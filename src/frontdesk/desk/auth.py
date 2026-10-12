"""Who may call the conversation deployment: a customer, with the token Keycloak signed for them.

The person's id becomes the owner of every thread they start, and they read no thread but their own. Their token
travels with the run, so that the agent's calls to the access server are made as that person and not as the
deployment. The server stores it with the run; it expires an hour after Keycloak signed it.
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
    if caller.role is None:
        raise Auth.exceptions.HTTPException(status_code=403, detail="You are not a member of a Quillstack workspace.")
    return {"identity": caller.person_id, "display_name": caller.username, "permissions": [caller.role], "token": caller.token}


@auth.on
async def own(ctx: Auth.types.AuthContext, value: dict) -> dict:
    """Threads and their runs: a person's own. What they create is stamped with their id, and everything else is
    filtered by it."""
    mine = {"owner": ctx.user.identity}
    value.setdefault("metadata", {}).update(mine)
    return mine


@auth.on.assistants
async def assistants(ctx: Auth.types.AuthContext, value: dict) -> bool:
    """The deployment's graphs can be looked up and run, and a customer changes none of them."""
    return ctx.action in ("read", "search")


@auth.on.crons
async def crons(ctx: Auth.types.AuthContext, value: dict) -> bool:
    return False


@auth.on.store
async def store(ctx: Auth.types.AuthContext, value: dict) -> bool:
    """Memory is read and written by the agent, on the person's behalf, and not over HTTP."""
    return False
