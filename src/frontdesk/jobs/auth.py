"""Who may call the jobs deployment: Quillstack's own services, and no customer.

The dispatcher starts and resumes the workers' runs, with a token Keycloak gives the client frontdesk-service. That
token carries the role "service". A customer's token is refused here whatever it asks for: a customer's agent
reaches a worker only through a request row, which the dispatcher picks up.
"""

from langgraph_sdk import Auth

from frontdesk import identity

auth = Auth()


@auth.authenticate
async def authenticate(authorization: str | None) -> Auth.types.MinimalUserDict:
    try:
        caller = await identity.abearer(authorization)
    except identity.NotSignedIn as e:
        raise Auth.exceptions.HTTPException(status_code=401, detail=str(e)) from e
    if "service" not in caller.roles:
        raise Auth.exceptions.HTTPException(status_code=403, detail="The jobs deployment serves Quillstack's services only.")
    return {"identity": caller.username, "permissions": ["service"]}


@auth.on
async def service_only(ctx: Auth.types.AuthContext, value: dict) -> bool:
    return "service" in ctx.permissions
