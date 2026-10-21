import asyncio

from fastmcp import Client


def test_profile_is_masked(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DB", str(tmp_path / "t.db"))
    import importlib

    import coach.config
    import mcp_servers.user_server as us
    importlib.reload(coach.config)
    importlib.reload(us)

    async def go():
        async with Client(us.mcp) as c:
            p = (await c.call_tool("get_profile", {"user_id": "u02"})).data["profile"]
            r = (await c.call_tool("log_record", {"user_id": "u02", "text": "walked 20 min"})).data
            n = (await c.call_tool("delete_record", {"user_id": "u02", "record_id": r["id"]})).data
            return p, n
    p, n = asyncio.run(go())
    assert "Daniel" not in p and "Kim" not in p and "neuropathy" in p
    assert n["deleted"] == 1
