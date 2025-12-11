# Backend Intern Assignment - My understanding

--- 

## Base Requirements

This is backend service needs all this : 
- FastAPI things needed : 
    - `POST /org/create` : Create organization
    - `GET /org/get` : Get details of organization
    - `PUT /org/update` : Updation of organization
    - `DELETE /org/delete` : Delete organization
    - `POST /admin/login` : Login
- Database things needed : 
    - Master Database : for metadata collection of dynamic collection.
    - Dynamic Collection : Isolated mongo collection
    - Authentication : Hashed passwords and Login of admin through JWT


All this looks like to make a basic CRUD operations through API's.

