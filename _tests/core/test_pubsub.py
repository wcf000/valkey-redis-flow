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
from app.core.valkey_core.client import client as valkey_client


import time

@pytest.mark.asyncio
def _wait_for_subscribe(pubsub, expected=1):
    # Wait for 'subscribe' confirmation(s)
    count = 0
    while count < expected:
        msg = asyncio.get_event_loop().run_until_complete(pubsub.get_message(timeout=2))
        if msg and msg.get('type') == 'subscribe':
            count += 1

async def _collect_messages(pubsub, count, timeout=2):
    # Collect up to 'count' messages or until timeout
    received = []
    start = time.time()
    while len(received) < count and (time.time() - start) < timeout:
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
        if msg:
            received.append(msg)
    return received

@pytest.mark.asyncio
async def test_pubsub_publish_subscribe(valkey_client):
    """Test that pubsub can publish and receive messages."""
    client = valkey_client
    pubsub = await client.pubsub()
    channel = "test_channel"
    message = "hello-valkey"

    await pubsub.subscribe(channel)
    await pubsub.get_message()  # Wait for subscription confirmation
    await client.publish(channel, message)
    # Try up to 3 times to get the message
    msg = None
    for _ in range(3):
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
        if msg:
            break
    assert msg is not None
    assert (msg["data"].decode() if isinstance(msg["data"], bytes) else msg["data"]) == message
    await pubsub.unsubscribe(channel)

@pytest.mark.asyncio
async def test_pubsub_multiple_messages(valkey_client):
    """Test pubsub receives multiple published messages in order."""
    client = valkey_client
    pubsub = await client.pubsub()
    channel = "test_channel_multi"
    messages = ["msg1", "msg2", "msg3"]
    await pubsub.subscribe(channel)
    await pubsub.get_message()  # Wait for subscription confirmation
    for msg in messages:
        await client.publish(channel, msg)
    # Collect up to len(messages) messages, allow a few seconds
    received_msgs = []
    start = time.time()
    while len(received_msgs) < len(messages) and (time.time() - start) < 5:
        m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
        if m:
            received_msgs.append(m["data"].decode() if isinstance(m["data"], bytes) else m["data"])
    assert received_msgs == messages
    await pubsub.unsubscribe(channel)

@pytest.mark.asyncio
async def test_pubsub_multiple_channels(valkey_client):
    """Test subscribing to multiple channels and receiving correct messages."""
    client = valkey_client
    pubsub = await client.pubsub()
    channels = ["chan1", "chan2"]
    await pubsub.subscribe(*channels)
    for _ in channels:
        await pubsub.get_message()  # Wait for each subscription confirmation
    await client.publish("chan1", "foo")
    await client.publish("chan2", "bar")
    # Collect up to 2 messages, allow a few seconds
    received = set()
    start = time.time()
    while len(received) < 2 and (time.time() - start) < 5:
        m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
        if m:
            received.add((m["channel"].decode() if isinstance(m["channel"], bytes) else m["channel"], m["data"].decode() if isinstance(m["data"], bytes) else m["data"]))
    assert ("chan1", "foo") in received
    assert ("chan2", "bar") in received
    await pubsub.unsubscribe(*channels)

@pytest.mark.asyncio
async def test_pubsub_unsubscribe_behavior(valkey_client):
    """Test unsubscribing stops message delivery."""
    client = valkey_client
    pubsub = await client.pubsub()
    channel = "test_unsub"
    await pubsub.subscribe(channel)
    await pubsub.unsubscribe(channel)
    await client.publish(channel, "should_not_receive")
    m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
    assert m is None

@pytest.mark.asyncio
async def test_pubsub_concurrent_publishers(valkey_client):
    """Test concurrent publishers deliver all messages to a single subscriber."""
    client = valkey_client
    pubsub = await client.pubsub()
    channel = "test_concurrent"
    await pubsub.subscribe(channel)
    await pubsub.get_message()  # Wait for subscription confirmation
    messages = [f"msg{i}" for i in range(5)]
    async def publisher(msg):
        await client.publish(channel, msg)
    await asyncio.gather(*(publisher(m) for m in messages))
    # Timed loop to collect all messages
    received = set()
    start = time.time()
    while len(received) < len(messages) and (time.time() - start) < 5:
        m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
        if m:
            received.add(m["data"].decode() if isinstance(m["data"], bytes) else m["data"])
    assert set(messages) == received
    await pubsub.unsubscribe(channel)

@pytest.mark.asyncio
async def test_pubsub_late_subscriber(valkey_client):
    """Test that a subscriber joining after a message is published does not receive old messages."""
    client = valkey_client
    channel = "test_late_sub"
    await client.publish(channel, "early_msg")
    pubsub = await client.pubsub()
    await pubsub.subscribe(channel)
    m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
    assert m is None
    await pubsub.unsubscribe(channel)

@pytest.mark.asyncio
async def test_pubsub_empty_message(valkey_client):
    """Test publishing and receiving an empty message."""
    client = valkey_client
    pubsub = await client.pubsub()
    channel = "test_empty"
    await pubsub.subscribe(channel)
    await pubsub.get_message()  # Wait for subscription confirmation
    await client.publish(channel, "")
    # Try to receive the message in a timed loop
    m = None
    start = time.time()
    while (time.time() - start) < 2:
        m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
        if m:
            break
    assert m is not None
    assert (m["data"].decode() if isinstance(m["data"], bytes) else m["data"]) == ""
    await pubsub.unsubscribe(channel)
    await pubsub.close()

@pytest.mark.asyncio
async def test_pubsub_channel_cleanup(valkey_client):
    """Test that channels are cleaned up after unsubscribe."""
    client = valkey_client
    pubsub = await client.pubsub()
    channel = "test_cleanup"
    await pubsub.subscribe(channel)
    await pubsub.unsubscribe(channel)
    # The pubsub object should no longer have the channel
    assert channel not in getattr(pubsub, "channels", {})
