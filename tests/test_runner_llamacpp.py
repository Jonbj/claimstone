"""The local server runner. No socket: the transport is injected."""

from claimstone.runners import llamacpp
from tests.test_runner_ollama import FakePost, request


def runner(post, **kw):
    return llamacpp.LlamaCppRunner(post=post, **kw)


def test_the_prefix_is_its_own_message_here_too():
    post = FakePost({"choices": [{"message": {"content": "[]"}, "finish_reason": "stop"}]})
    runner(post).run(request())
    assert [m["role"] for m in post.sent["messages"]] == ["system", "user"]


def test_the_local_server_is_serial():
    # Measured at 11.6 minutes per call on the target machine: a second concurrent call does
    # not halve that, it queues behind the first on one GPU.
    assert runner(FakePost({})).max_concurrency == 1


def test_a_local_call_is_unpriced_because_it_has_no_price():
    post = FakePost({"choices": [{"message": {"content": "[]"}, "finish_reason": "stop"}],
                     "usage": {"prompt_tokens": 10, "completion_tokens": 5}})
    answer = runner(post).run(request())
    assert answer.cost_usd is None
    assert answer.usage == {"input_tokens": 10, "output_tokens": 5}


def test_a_length_finish_is_truncated():
    post = FakePost({"choices": [{"message": {"content": "[{"}, "finish_reason": "length"}]})
    assert runner(post).run(request()).truncated is True


def test_a_dead_server_is_a_backend_error():
    def refuse(*args, **kwargs):
        raise OSError("connection refused")

    assert runner(refuse).run(request()).failure_class == "BACKEND_ERROR"
