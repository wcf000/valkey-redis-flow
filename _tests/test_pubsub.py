"""
Comprehensive tests for Valkey pubsub functionality using async client.
Covers:
- Basic publish/subscribe
- Multiple messages
- Multiple channels
- Unsubscribe
- Pubsub with concurrent publishers/subscribers
- Edge cases (empty message, late subscriber, channel cleanup)
"""
import asyncio
import pytest
from app.core.valkey.client import client as valkey_client

@pytest.mark.asyncio
async def test_pubsub_publish_subscribe():
    """Test that pubsub can publish and receive messages."""
    client = valkey_client
    pubsub = await client.pubsub()
    channel = "test_channel"
    message = "hello-valkey"

    await pubsub.subscribe(channel)
    await (await client.get_client()).publish(channel, message)
    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
    assert msg is not None
    assert msg["data"] == message
    await pubsub.unsubscribe(channel)

@pytest.mark.asyncio
async def test_pubsub_multiple_messages():
    """Test pubsub receives multiple published messages in order."""
    client = valkey_client
    pubsub = await client.pubsub()
    channel = "test_channel_multi"
    messages = ["msg1", "msg2", "msg3"]
    await pubsub.subscribe(channel)
    for msg in messages:
        await (await client.get_client()).publish(channel, msg)
    received = []
    for _ in messages:
        m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
        if m:
            received.append(m["data"])
    assert received == messages
    await pubsub.unsubscribe(channel)

@pytest.mark.asyncio
async def test_pubsub_multiple_channels():
    """Test subscribing to multiple channels and receiving correct messages."""
    client = valkey_client
    pubsub = await client.pubsub()
    channels = ["chan1", "chan2"]
    await pubsub.subscribe(*channels)
    await (await client.get_client()).publish("chan1", "foo")
    await (await client.get_client()).publish("chan2", "bar")
    received = set()
    for _ in range(2):
        m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
        if m:
            received.add((m["channel"], m["data"]))
    assert ("chan1", "foo") in received
    assert ("chan2", "bar") in received
    await pubsub.unsubscribe(*channels)

@pytest.mark.asyncio
async def test_pubsub_unsubscribe_behavior():
    """Test unsubscribing stops message delivery."""
    client = valkey_client
    pubsub = await client.pubsub()
    channel = "test_unsub"
    await pubsub.subscribe(channel)
    await pubsub.unsubscribe(channel)
    await (await client.get_client()).publish(channel, "should_not_receive")
    m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
    assert m is None

@pytest.mark.asyncio
async def test_pubsub_concurrent_publishers():
    """Test concurrent publishers deliver all messages to a single subscriber."""
    client = valkey_client
    pubsub = await client.pubsub()
    channel = "test_concurrent"
    await pubsub.subscribe(channel)
    messages = [f"msg{i}" for i in range(5)]
    async def publisher(msg):
        await (await client.get_client()).publish(channel, msg)
    await asyncio.gather(*(publisher(m) for m in messages))
    received = set()
    for _ in messages:
        m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
        if m:
            received.add(m["data"])
    assert set(messages) == received
    await pubsub.unsubscribe(channel)

@pytest.mark.asyncio
async def test_pubsub_late_subscriber():
    """Test that a subscriber joining after a message is published does not receive old messages."""
    client = valkey_client
    channel = "test_late_sub"
    await (await client.get_client()).publish(channel, "early_msg")
    pubsub = await client.pubsub()
    await pubsub.subscribe(channel)
    m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
    assert m is None
    await pubsub.unsubscribe(channel)

@pytest.mark.asyncio
async def test_pubsub_empty_message():
    """Test publishing and receiving an empty message."""
    client = valkey_client
    pubsub = await client.pubsub()
    channel = "test_empty"
    await pubsub.subscribe(channel)
    await (await client.get_client()).publish(channel, "")
    m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
    assert m is not None
    assert m["data"] == ""
    await pubsub.unsubscribe(channel)

@pytest.mark.asyncio
async def test_pubsub_channel_cleanup():
    """Test that channels are cleaned up after unsubscribe."""
    client = valkey_client
    pubsub = await client.pubsub()
    channel = "test_cleanup"
    await pubsub.subscribe(channel)
    await pubsub.unsubscribe(channel)
    # The pubsub object should no longer have the channel
    assert channel not in getattr(pubsub, "channels", {})
