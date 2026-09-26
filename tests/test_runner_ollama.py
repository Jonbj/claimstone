"""The hosted-endpoint runner. No socket: the transport is injected."""

import json

from claimstone.runners import ollama_cloud


def request(**overrides):
    base = {"call_id": "abc", "lane": "extract", "system": "the registry", "user": "a chunk",
            "max_output_tokens": 800, "response_schema": {"type": "array"}}
    return {**base, **overrides}


class FakePost:
    """Stands in for requests.post. Records what it was sent."""

    def __init__(self, payload, status=200):
        self.payload, self.status = payload, status
        self.sent: dict = {}
        self.headers: dict = {}

    def __call__(self, url, *, json=None, headers=None, timeout=None):
        self.sent, self.headers = json or {}, headers or {}

        class Response:
            status_code = self.status
            text = "server said so"

            def json(inner):
                return self.payload

        return Response()


# A key that cannot collide with anything else in the body. The first version used "k", and the
# assertion "k" not in the body failed on the letter k in "deepseek" — a one-character substring
# test verifies nothing.
API_KEY = "sk-test-NOTINTHEBODY-7f3a"


def runner(post, **kw):
    return ollama_cloud.OllamaCloudRunner(
        model="deepseek-v4.1-flash", api_key=API_KEY, post=post, **kw)


def test_the_stable_prefix_is_sent_as_its_own_message():
    # The registry is identical across every call in a lane. Keeping it in its own system
    # message is what lets a backend charge it as cached input — $0.006 against $0.30 per
    # MTok, fifty-fold — and it puts the cacheability in the file rather than in the runner.
    post = FakePost({"message": {"content": "[]"}})
    runner(post).run(request())
    roles = [m["role"] for m in post.sent["messages"]]
    assert roles == ["system", "user"]
    assert post.sent["messages"][0]["content"] == "the registry"


def test_the_output_cap_is_passed_through():
    post = FakePost({"message": {"content": "[]"}})
    runner(post).run(request(max_output_tokens=800))
    assert post.sent["options"]["num_predict"] == 800


def test_the_api_key_travels_in_the_header_not_the_body():
    post = FakePost({"message": {"content": "[]"}})
    runner(post).run(request())
    assert API_KEY in post.headers.get("Authorization", "")
    assert API_KEY not in json.dumps(post.sent)


def test_usage_and_cost_are_carried_when_the_endpoint_reports_them():
    post = FakePost({"message": {"content": "[]"},
                     "prompt_eval_count": 3841, "eval_count": 412})
    answer = runner(post, price_in=0.30, price_out=1.20).run(request())
    assert answer.usage == {"input_tokens": 3841, "output_tokens": 412}
    assert answer.cost_usd == round(3841 / 1e6 * 0.30 + 412 / 1e6 * 1.20, 8)


def test_without_declared_prices_the_call_is_unpriced_not_free():
    post = FakePost({"message": {"content": "[]"}, "prompt_eval_count": 10, "eval_count": 5})
    assert runner(post).run(request()).cost_usd is None


def test_a_cut_off_answer_is_reported_as_truncated():
    post = FakePost({"message": {"content": "[{"}, "done_reason": "length"})
    assert runner(post).run(request()).truncated is True


def test_a_429_is_rate_limited():
    post = FakePost({}, status=429)
    assert runner(post).run(request()).failure_class == "RATE_LIMITED"


def test_a_500_is_a_backend_error():
    post = FakePost({}, status=500)
    assert runner(post).run(request()).failure_class == "BACKEND_ERROR"


def test_the_prompt_sent_is_reported_as_the_joining_of_the_two_messages():
    """It sends two messages; the echo check compares one string. rendered_prompt is that string,
    and reporting it is what makes prompt_verified mean something for this backend."""
    from claimstone import model_call

    post = FakePost({"message": {"content": "[]"}})
    req = request()
    answer = runner(post).run(req)
    assert answer.prompt_sent == model_call.rendered_prompt(req["system"], req["user"])


def test_cached_input_can_be_priced_separately():
    """The docstring's whole argument is that cached input costs a fiftieth. Charging it at the
    fresh rate overstates the bill for exactly the saving this backend was chosen for."""
    post = FakePost({"message": {"content": "[]"}, "prompt_eval_count": 4000,
                     "eval_count": 100, "prompt_cache_hit_count": 3800})
    answer = runner(post, price_in=0.30, price_out=1.20, price_cached_in=0.006).run(request())
    assert answer.usage["cached_input_tokens"] == 3800
    expected = (200 / 1e6 * 0.30) + (3800 / 1e6 * 0.006) + (100 / 1e6 * 1.20)
    assert answer.cost_usd == round(expected, 8)


def test_without_a_cached_price_cached_tokens_cost_the_full_rate():
    """The conservative reading, and it is the one that cannot understate a bill."""
    post = FakePost({"message": {"content": "[]"}, "prompt_eval_count": 4000,
                     "eval_count": 100, "prompt_cache_hit_count": 3800})
    answer = runner(post, price_in=0.30, price_out=1.20).run(request())
    assert answer.cost_usd == round(4000 / 1e6 * 0.30 + 100 / 1e6 * 1.20, 8)
