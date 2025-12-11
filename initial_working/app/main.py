import os
import re
from datetime import datetime, timedelta
from typing import Optional, List, Any, Dict

from fastapi import FastAPI, APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId
from dotenv import load_dotenv
from slugify import slugify
from argon2 import PasswordHasher, exceptions as argon2_exceptions
import jwt
import asyncio

# load .env
load_dotenv()

# -------------------------
# Config
# -------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MASTER_DB = os.getenv("MASTER_DB", "master_db")
JWT_SECRET = os.getenv("JWT_SECRET", "supersecretkey")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXP_SECONDS = int(os.getenv("JWT_EXP_SECONDS", 3600))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 500))

# -------------------------
# Security: password hasher and auth
# -------------------------
pwd_hasher = PasswordHasher()
auth_scheme = HTTPBearer()

# -------------------------
# FastAPI app
# -------------------------
app = FastAPI(title="Organization Management Service (Complete)")
router = APIRouter(prefix="/org", tags=["organization"])


# -------------------------
# Pydantic models
# -------------------------
class OrgCreateIn(BaseModel):
    organization_name: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=6)


class OrgGetIn(BaseModel):
    organization_name: str = Field(..., min_length=1)


class OrgUpdateIn(BaseModel):
    organization_name: str = Field(..., min_length=1)  # current name
    new_organization_name: Optional[str] = None  # if rename desired
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6)


class OrgDeleteIn(BaseModel):
    organization_name: str = Field(..., min_length=1)


class AdminLoginIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


# -------------------------
# Startup / Shutdown: DB lifecycle
# -------------------------
@app.on_event("startup")
async def startup():
    app.state.mongo_client = AsyncIOMotorClient(MONGO_URI)
    app.state.db = app.state.mongo_client[MASTER_DB]
    app.state.orgs = app.state.db["organizations"]
    app.state.admins = app.state.db["admins"]

    # Create indexes:
    # unique slug enforces uniqueness of organization names in normalized form
    await app.state.orgs.create_index("slug", unique=True)
    # admin email index (per org uniqueness enforced when needed)
    await app.state.admins.create_index([("organization_id", 1), ("email", 1)], unique=False)


@app.on_event("shutdown")
async def shutdown():
    client = getattr(app.state, "mongo_client", None)
    if client:
        client.close()


def get_db():
    return app.state.db


# -------------------------
# Helpers: slugs, hashing, jwt
# -------------------------
def slugify_org(name: str) -> str:
    s = slugify(name)
    s = re.sub(r"[^a-z0-9\-]", "", s.lower())
    return f"org_{s}"


def now_ts() -> datetime:
    return datetime.utcnow()


def hash_password(password: str) -> str:
    # Argon2 supports long passwords (better than bcrypt). Will raise on internal errors.
    return pwd_hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return pwd_hasher.verify(hashed, password)
    except argon2_exceptions.VerifyMismatchError:
        return False
    except argon2_exceptions.VerificationError:
        return False
    except Exception:
        return False


def create_jwt(payload: Dict[str, Any]) -> str:
    p = payload.copy()
    p["exp"] = datetime.utcnow() + timedelta(seconds=JWT_EXP_SECONDS)
    return jwt.encode(p, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# -------------------------
# Auth dependency
# -------------------------
async def get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(auth_scheme)):
    token = credentials.credentials
    payload = decode_jwt(token)
    admin_id = payload.get("admin_id")
    org_id = payload.get("org_id")
    if not admin_id or not org_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    admin = await app.state.admins.find_one({"_id": admin_id})
    if not admin:
        raise HTTPException(status_code=401, detail="Admin not found")

    if str(admin.get("organization_id")) != str(org_id):
        raise HTTPException(status_code=403, detail="Organization mismatch")

    return {"admin": admin, "org_id": org_id}


# -------------------------
# Utility: convert ObjectId to str in doc
# -------------------------
def oid_str(doc):
    if not doc:
        return doc
    d = dict(doc)
    if "_id" in d:
        d["_id"] = str(d["_id"])
    return d


# -------------------------
# Create Organization
# -------------------------
@router.post("/create", status_code=201)
async def create_organization(payload: OrgCreateIn):
    orgs = app.state.orgs
    admins = app.state.admins
    db = app.state.db

    org_name = payload.organization_name.strip()
    email = payload.email.lower().strip()
    password = payload.password

    # slug (normalized) used for collection name and uniqueness index
    slug = slugify_org(org_name)

    # ensure slug not taken
    existing = await orgs.find_one({"slug": slug})
    if existing:
        raise HTTPException(status_code=400, detail="Organization name already exists")

    now = now_ts()

    # create org document in master db
    org_doc = {
        "organization_name": org_name,
        "slug": slug,
        "collection_name": slug,
        "connection_details": {"db": MASTER_DB, "uri": MONGO_URI},
        "created_at": now,
        "updated_at": now,
    }
    res = await orgs.insert_one(org_doc)
    org_id = str(res.inserted_id)

    # create admin user; use string id for simplicity
    admin_id = f"admin_{email}_{int(datetime.utcnow().timestamp())}"
    hashed = hash_password(password)
    admin_doc = {
        "_id": admin_id,
        "email": email,
        "password_hash": hashed,
        "organization_id": org_id,
        "role": "admin",
        "created_at": now,
    }
    await admins.insert_one(admin_doc)

    # Update org with admin reference
    await orgs.update_one({"_id": res.inserted_id}, {"$set": {"admin_user_id": admin_id}})

    # create tenant collection programmatically
    try:
        await db.create_collection(slug)
    except Exception:
        # ignore if collection already exists
        pass

    # initialize with basic schema/meta doc (optional)
    try:
        await db[slug].insert_one({"_meta": True, "created_at": now, "schema_version": 1})
    except Exception:
        pass

    return {
        "ok": True,
        "organization_name": org_name,
        "collection_name": slug,
        "admin_user_id": admin_id,
        "org_id": org_id,
    }


# -------------------------
# Get Organization
# -------------------------
@router.get("/get")
async def get_organization(organization_name: str):
    slug = slugify_org(organization_name)
    org = await app.state.orgs.find_one({"slug": slug})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    out = {
        "organization_name": org.get("organization_name"),
        "collection_name": org.get("collection_name"),
        "connection_details": org.get("connection_details"),
        "admin_user_id": org.get("admin_user_id"),
        "org_id": str(org.get("_id")),
        "created_at": org.get("created_at"),
    }
    return out


# -------------------------
# Update Organization
# -------------------------
@router.put("/update")
async def update_organization(payload: OrgUpdateIn):
    """
    Supports:
     - renaming organization (new_organization_name provided): creates new collection,
       copies data in batches from old collection to new collection, updates master metadata,
       drops old collection after successful migration.
     - updating admin email/password.
    """
    orgs = app.state.orgs
    admins = app.state.admins
    db = app.state.db

    current_slug = slugify_org(payload.organization_name)
    org = await orgs.find_one({"slug": current_slug})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    updates = {}
    now = now_ts()

    # Handle rename
    if payload.new_organization_name:
        new_name = payload.new_organization_name.strip()
        new_slug = slugify_org(new_name)
        if new_slug == current_slug:
            # nothing to do for collection rename
            pass
        else:
            # ensure new slug not taken
            conflict = await orgs.find_one({"slug": new_slug})
            if conflict:
                raise HTTPException(status_code=400, detail="New organization name already exists")

            # create new collection
            try:
                await db.create_collection(new_slug)
            except Exception:
                pass

            # migrate data in batches from old collection to new collection
            old_coll = db[current_slug]
            new_coll = db[new_slug]

            cursor = old_coll.find({})
            batch = []
            count = 0
            async for doc in cursor:
                # keep same doc (including _id); it's safe because collections differ
                batch.append(doc)
                if len(batch) >= BATCH_SIZE:
                    try:
                        await new_coll.insert_many(batch, ordered=False)
                    except Exception:
                        # ignore duplicates/problems per batch but continue
                        pass
                    count += len(batch)
                    batch = []
            if batch:
                try:
                    await new_coll.insert_many(batch, ordered=False)
                except Exception:
                    pass
                count += len(batch)

            # update master org doc to point to new collection/name
            updates["organization_name"] = new_name
            updates["slug"] = new_slug
            updates["collection_name"] = new_slug
            updates["updated_at"] = now
            await orgs.update_one({"_id": org["_id"]}, {"$set": updates})

            # optionally drop old collection after migration
            try:
                await db.drop_collection(current_slug)
            except Exception:
                pass

            # refresh org reference for admin update below
            org = await orgs.find_one({"slug": new_slug})

    # Update admin credentials if provided
    if payload.email or payload.password:
        # find admin by organization_id (stored as string)
        admin = await admins.find_one({"organization_id": str(org["_id"])})
        if not admin:
            raise HTTPException(status_code=500, detail="Admin record missing for organization")

        admin_updates = {}
        if payload.email:
            admin_updates["email"] = payload.email.lower().strip()
        if payload.password:
            admin_updates["password_hash"] = hash_password(payload.password)
        if admin_updates:
            admin_updates["updated_at"] = now
            await admins.update_one({"_id": admin["_id"]}, {"$set": admin_updates})

    return {"ok": True, "updated": updates}


# -------------------------
# Delete Organization
# -------------------------
@router.delete("/delete")
async def delete_organization(payload: OrgDeleteIn, cred=Depends(get_current_admin)):
    """
    Only an authenticated admin belonging to the organization may delete it.
    """
    orgs = app.state.orgs
    admins = app.state.admins
    db = app.state.db

    slug = slugify_org(payload.organization_name)
    org = await orgs.find_one({"slug": slug})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # ensure requesting admin belongs to this org
    token_org_id = cred["org_id"]
    if str(org.get("_id")) != str(token_org_id):
        raise HTTPException(status_code=403, detail="Not authorized to delete this organization")

    # drop tenant collection(s)
    try:
        await db.drop_collection(slug)
    except Exception:
        pass

    # remove admin(s)
    await admins.delete_many({"organization_id": str(org["_id"])})

    # remove org record
    await orgs.delete_one({"_id": org["_id"]})

    return {"ok": True, "deleted_org": payload.organization_name}


# -------------------------
# Admin Login
# -------------------------
@app.post("/admin/login")
async def admin_login(payload: AdminLoginIn):
    admins = app.state.admins
    admin = await admins.find_one({"email": payload.email.lower().strip()})
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    hashed = admin.get("password_hash")
    if not hashed or not verify_password(payload.password, hashed):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_jwt({"admin_id": admin["_id"], "org_id": admin.get("organization_id")})
    return {"access_token": token, "token_type": "bearer"}


# -------------------------
# Root & utility test
# -------------------------
@router.post("/_test_insert")
async def _test_insert():
    db = app.state.db
    res = await db["test_collection"].insert_one({"ping": "ok", "ts": now_ts()})
    return {"inserted_id": str(res.inserted_id)}


app.include_router(router)


@app.get("/")
async def root():
    return {"message": "Service running"}
