# Initial Plan

I am going to do this in my Fedora, So commands may vary.

#### Python initialization and Some files creation

I am going to use Python 3.12 , so before that some system needs : 

`sudo dnf install -y @development-tools openssl-devel bzip2-devel libffi-devel zlib-devel readline-devel sqlite-devel wget curl git
`

Then, we are going to use pyenv for cleaner build of python : 

```curl https://pyenv.run | bash
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init --path)"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
exec $SHELL

pyenv install 3.12.0
pyenv local 3.12.0       # do it inside the folder u need

```

Virtual environment intialization,

```
python -m venv venv
source venv/bin/activate
```

Files needed for now,
- .env
- requirements.txt
- .gitignore

For FastAPI,
- Create a folder called app
- Inside that a main.py


#### FastAPI code (Empty routes)

For now lets just keep a empty routes kind of code, then add code

```
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status
from typing import Optional

app = FastAPI(title="Organization Service - Initial Base")

router = APIRouter(prefix="/org", tags=["org"])

class OrgService:
    """
    Service layer placeholder for organization operations.
    Will implement logic step-by-step later.
    For now, it only contains method stubs.
    """
    def __init__(self):
        pass

    async def create_org(self, organization_name: str, email: str, password: str):
        # TODO: implement creation logic later
        pass

    async def get_org(self, organization_name: str):
        # TODO: implement retrieval logic later
        pass

    async def update_org(self, organization_name: str, email: Optional[str], password: Optional[str]):
        # TODO: implement update logic later
        pass

    async def delete_org(self, organization_name: str):
        # TODO: implement deletion logic later
        pass

# instantiate the service
org_service = OrgService()

@router.post("/create")
async def create_org_route(organization_name: str, email: str, password: str):
    await org_service.create_org(organization_name, email, password)
    return {"ok": True, "organization_name": organization_name}

@router.get("/get")
async def get_org_route(organization_name: str):
    result = await org_service.get_org(organization_name)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )
    return {"ok": True, "data": result}

@router.put("/update")
async def update_org_route(
    organization_name: str,
    email: Optional[str] = None,
    password: Optional[str] = None
):
    await org_service.update_org(organization_name, email, password)
    return {"ok": True}

@router.delete("/delete")
async def delete_org_route(organization_name: str):
    await org_service.delete_org(organization_name)
    return {"ok": True}

# include router
app.include_router(router)

@app.get("/")
async def root():
    return {"message": "App is running"}

```


