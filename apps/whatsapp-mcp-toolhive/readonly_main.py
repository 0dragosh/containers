import signal
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from message_search import search_messages as whatsapp_search_messages
from whatsapp import download_media as whatsapp_download_media
from whatsapp import get_chat as whatsapp_get_chat
from whatsapp import get_contact_chats as whatsapp_get_contact_chats
from whatsapp import get_direct_chat_by_contact as whatsapp_get_direct_chat_by_contact
from whatsapp import get_last_interaction as whatsapp_get_last_interaction
from whatsapp import get_message_context as whatsapp_get_message_context
from whatsapp import get_sender_name as whatsapp_get_sender_name
from whatsapp import list_chats as whatsapp_list_chats
from whatsapp import list_messages as whatsapp_list_messages
from whatsapp import msg_to_dict
from whatsapp import search_contacts as whatsapp_search_contacts
from whatsapp import _sender_aliases as whatsapp_sender_aliases

mcp = FastMCP("whatsapp")


@mcp.tool()
def search_contacts(query: str) -> list[dict[str, Any]]:
    """Search WhatsApp contacts by name or phone number."""
    return whatsapp_search_contacts(query)


@mcp.tool()
def get_contact(
    identifier: str | None = None,
    phone_number: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    """Look up a WhatsApp contact by phone number, LID, or full JID."""
    if identifier is None:
        identifier = phone_number
    if identifier is None:
        identifier = phone
    if identifier is None:
        raise ValueError(
            "Missing required argument: identifier (or phone_number / phone)"
        )

    identifier = identifier.strip()
    if not identifier:
        raise ValueError("identifier must be non-empty")

    bare_numeric_digits: str | None = None
    if "@" in identifier:
        jid = identifier
        is_lid = jid.endswith("@lid") or jid.split("@", 1)[-1] == "lid"
    else:
        digits = "".join(c for c in identifier if c.isdigit())
        if digits:
            jid = f"{digits}@s.whatsapp.net"
            is_lid = False
            if identifier.isdigit():
                bare_numeric_digits = digits
        else:
            jid = identifier
            is_lid = False

    jid_user = jid.split("@", 1)[0]
    candidates: list[tuple[str, bool]] = [(jid, is_lid)]
    if bare_numeric_digits:
        candidates.append((f"{bare_numeric_digits}@lid", True))

    chat = None
    for candidate_jid, candidate_is_lid in candidates:
        chat = whatsapp_get_chat(candidate_jid, include_last_message=False)
        if chat:
            jid = candidate_jid
            is_lid = candidate_is_lid
            jid_user = jid.split("@", 1)[0]
            break

    if chat and chat.get("name"):
        display_name = chat["name"]
        resolved = display_name not in (jid, jid_user)
    else:
        display_name = whatsapp_get_sender_name(jid)
        resolved = display_name not in (jid, jid_user, identifier)

    return {
        "identifier": identifier,
        "jid": jid,
        "phone_number": jid_user if not is_lid else None,
        "lid": jid_user if is_lid else None,
        "name": display_name if resolved else jid_user,
        "display_name": display_name,
        "is_lid": is_lid,
        "resolved": resolved,
    }


@mcp.tool()
def list_messages(
    after: str | None = None,
    before: str | None = None,
    sender_phone_number: str | None = None,
    chat_jid: str | None = None,
    query: str | None = None,
    limit: int = 50,
    page: int = 0,
    include_context: bool = True,
    context_before: int = 1,
    context_after: int = 1,
    sort_by: str = "newest",
) -> list[dict[str, Any]]:
    """Get WhatsApp messages matching specified criteria with optional context."""
    return whatsapp_list_messages(
        after=after,
        before=before,
        sender_phone_number=sender_phone_number,
        chat_jid=chat_jid,
        query=query,
        limit=min(limit, 500),
        page=page,
        include_context=include_context,
        context_before=context_before,
        context_after=context_after,
        sort_by=sort_by,
    )


@mcp.tool()
def search_messages(
    query: str,
    chat_jid: str | None = None,
    sender_phone_number: str | None = None,
    after: str | None = None,
    before: str | None = None,
    ranking: str = "recent_relevance",
    limit: int = 6,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Search WhatsApp for ad hoc topics, decisions, and current status.

    Returns compact relevance-ranked conversation evidence. Use list_messages
    instead for chronological ranges and periodic summaries, then use
    get_message_context when a selected result needs deeper context.
    """
    aliases = (
        whatsapp_sender_aliases(sender_phone_number) if sender_phone_number else None
    )
    return whatsapp_search_messages(
        query=query,
        chat_jid=chat_jid,
        sender_phone_number=sender_phone_number,
        after=after,
        before=before,
        ranking=ranking,
        limit=limit,
        cursor=cursor,
        sender_aliases=aliases,
        sender_name_resolver=whatsapp_get_sender_name,
    )


@mcp.tool()
def list_chats(
    query: str | None = None,
    limit: int = 50,
    page: int = 0,
    include_last_message: bool = True,
    sort_by: str = "last_active",
) -> list[dict[str, Any]]:
    """Get WhatsApp chats matching specified criteria."""
    return whatsapp_list_chats(
        query=query,
        limit=min(limit, 200),
        page=page,
        include_last_message=include_last_message,
        sort_by=sort_by,
    )


@mcp.tool()
def get_chat(chat_jid: str, include_last_message: bool = True) -> dict[str, Any] | None:
    """Get WhatsApp chat metadata by JID."""
    return whatsapp_get_chat(chat_jid, include_last_message)


@mcp.tool()
def get_direct_chat_by_contact(sender_phone_number: str) -> dict[str, Any] | None:
    """Get WhatsApp chat metadata by sender phone number."""
    return whatsapp_get_direct_chat_by_contact(sender_phone_number)


@mcp.tool()
def get_contact_chats(jid: str, limit: int = 20, page: int = 0) -> list[dict[str, Any]]:
    """Get all WhatsApp chats involving the contact."""
    return whatsapp_get_contact_chats(jid, limit, page)


@mcp.tool()
def get_last_interaction(jid: str) -> dict[str, Any]:
    """Get most recent WhatsApp message involving the contact."""
    message = whatsapp_get_last_interaction(jid)
    return message if message else {}


@mcp.tool()
def get_message_context(
    message_id: str, before: int = 5, after: int = 5
) -> dict[str, Any]:
    """Get context around a specific WhatsApp message."""
    context = whatsapp_get_message_context(message_id, before, after)
    return {
        "message": msg_to_dict(context.message),
        "before": [msg_to_dict(message) for message in context.before],
        "after": [msg_to_dict(message) for message in context.after],
    }


@mcp.tool()
def download_media(message_id: str, chat_jid: str) -> dict[str, Any]:
    """Download media from a WhatsApp message and get the local file path."""
    file_path = whatsapp_download_media(message_id, chat_jid)
    if file_path:
        return {
            "success": True,
            "message": "Media downloaded successfully",
            "file_path": file_path,
        }
    return {"success": False, "message": "Failed to download media"}


def shutdown_handler(signum, frame):
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    mcp.run(transport="stdio")
