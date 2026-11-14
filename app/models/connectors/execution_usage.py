"""Usage normalization and explicit retry/timeout semantics for one SDK attempt."""
import asyncio


def conservative_tokens(text):
    # Byte-level upper estimate, not a tokenizer measurement. Include envelope slack.
    return len(text.encode("utf-8")) + 256


def usage_counts(usage, input_estimate, output_estimate):
    def get(name):
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    inputs = get("prompt_tokens")
    if inputs is None:
        inputs = get("prompt_token_count")
    outputs = get("completion_tokens")
    if outputs is None:
        outputs = get("candidates_token_count")
        thoughts = get("thoughts_token_count")
        if outputs is not None and thoughts is not None:
            outputs += thoughts
    total = get("total_tokens")
    if total is None:
        total = get("total_token_count")
    breakdown_estimated = inputs is None and outputs is None
    if total is not None:
        if inputs is None and outputs is not None and outputs <= total:
            inputs = total - outputs
        elif outputs is None and inputs is not None and inputs <= total:
            outputs = total - inputs
        elif inputs is None and outputs is None:
            inputs = min(input_estimate, total)
            outputs = total - inputs
        if inputs is not None and total >= inputs:
            outputs = max(outputs or 0, total - inputs)
    reported = inputs is not None and outputs is not None
    inputs = inputs if inputs is not None else input_estimate
    outputs = outputs if outputs is not None else output_estimate
    total = max(total or 0, inputs + outputs)
    return {"input_tokens": inputs, "output_tokens": outputs, "total_tokens": total,
            "usage_source": "provider_reported" if reported else "estimated",
            "usage_breakdown_estimated": breakdown_estimated or not reported}



class ProviderCallError(RuntimeError):
    def __init__(self, message, *, retryable=False, request_sent=True, usage=None):
        super().__init__(message)
        self.retryable = retryable
        self.request_sent = request_sent
        self.usage = usage


class ProviderTimeoutError(asyncio.TimeoutError):
    def __init__(self, message, *, request_sent=True, usage=None):
        super().__init__(message)
        self.retryable = False
        self.request_sent = request_sent
        self.usage = usage
        self.cancellation_uncertain = request_sent


def exception_usage(error):
    usage = getattr(error, "usage", None)
    if usage is None:
        usage = getattr(error, "usage_metadata", None)
    body = getattr(error, "body", None)
    if usage is None and isinstance(body, dict):
        usage = body.get("usage") or body.get("usage_metadata")
    return usage


async def bounded_await(awaitable, timeout, *, pending=None, request_sent=True):
    """Bound the local wait even if cancellation is delayed by the underlying client.

    A pending SDK task stays visible to its adapter until it actually ends. A local
    timeout never asserts that the remote service stopped or refunded the request.
    """
    task = asyncio.ensure_future(awaitable)
    if pending is not None:
        pending.add(task)
    def finished(done):
        if pending is not None:
            pending.discard(done)
        if not done.cancelled():
            done.exception()  # Consume a late failure without leaking task warnings.
    task.add_done_callback(finished)
    try:
        done, _ = await asyncio.wait({task}, timeout=timeout)
        if done:
            return task.result()
        task.cancel()
        raise ProviderTimeoutError(
            f"Timed out after {timeout}s; cancellation requested, remote completion and billing are unknown",
            request_sent=request_sent,
        )
    except asyncio.CancelledError:
        task.cancel()
        raise
