"""What an account or people route does once it is allowed to: the ledger calls and the
session revocations that must go with them. HTTP, cookies and the envelope stay in control.py."""

from __future__ import annotations

import pathlib
from typing import Any

from claimstone import auth_events, operators


class AccountError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def public(person: dict[str, Any]) -> dict[str, Any]:
    """A person as the portal may see them: never a salt, a hash or a subject."""
    return {"id": person["id"], "name": person["name"], "role": person["role"],
            "email": person["email"], "enabled": person["enabled"],
            "google_linked": bool(person["google_sub"])}


def _refuse(exc: operators.OperatorError) -> AccountError:
    if str(exc).startswith("unknown operator"):
        return AccountError(404, "NOT_FOUND", str(exc))
    return AccountError(422, "VALIDATION", str(exc))


def change_own_password(state: pathlib.Path, operator_id: str, new: object) -> None:
    """Validate and write the new password. The caller has already re-authenticated."""
    try:
        operators.set_password(state, operator_id, new, by=operator_id)  # type: ignore[arg-type]
    except operators.OperatorError as exc:
        raise _refuse(exc) from None
    auth_events.record(state, "password_changed", id=operator_id, by=operator_id)


def _text(value: object, field: str, *, optional: bool = False, longest: int = 10_000,
          shortest: int = 0) -> None:
    """A field that must be a string (or, when optional, absent/None): any other type is a 422."""
    if value is None and optional:
        return
    if not isinstance(value, str) or not shortest <= len(value.strip()) <= longest:
        raise AccountError(422, "VALIDATION", f"{field} must be text"
                           + (f" of {shortest}-{longest} characters" if shortest else ""))


def create_person(state: pathlib.Path, actor: str, body: dict[str, Any]) -> dict[str, Any]:
    person_id = body.get("id")
    name = body.get("name")
    if not isinstance(person_id, str):
        raise AccountError(422, "VALIDATION", "id must be text")
    _text(name, "name", shortest=1, longest=100)
    _text(body.get("email"), "email", optional=True)
    if body.get("role") is not None:
        _text(body.get("role"), "role")
    try:
        operators.add_operator(state, person_id, name, body.get("temporary_password"),  # type: ignore[arg-type]
                               role=body.get("role") or "operator",
                               email=body.get("email"), must_change=True, by=actor)
    except operators.OperatorError as exc:
        raise _refuse(exc) from None
    auth_events.record(state, "person_created", id=person_id, by=actor)
    return public(operators.people(state)[person_id])


def apply_to_person(state: pathlib.Path, actor: str, person_id: str, action: str,
                    body: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """(person, sessions_must_end). `action` is password | disable | enable | email | role."""
    try:
        if action == "password":
            operators.set_password(state, person_id, body.get("new_password"), by=actor,  # type: ignore[arg-type]
                                   must_change=True)
            auth_events.record(state, "password_set_by_admin", id=person_id, by=actor)
            ends = True
        elif action == "disable":
            operators.disable_operator(state, person_id, by=actor)
            auth_events.record(state, "person_disabled", id=person_id, by=actor)
            ends = True
        elif action == "enable":
            operators.enable_operator(state, person_id, by=actor)
            auth_events.record(state, "person_enabled", id=person_id, by=actor)
            ends = False
        elif action == "email":
            _text(body.get("email"), "email", optional=True)
            operators.set_email(state, person_id, body.get("email"), by=actor)
            auth_events.record(state, "person_email_set", id=person_id, by=actor)
            ends = False
        elif action == "role":
            _text(body.get("role"), "role")
            operators.set_role(state, person_id, body.get("role"), by=actor)
            auth_events.record(state, "person_role_set", id=person_id, by=actor)
            ends = False
        else:  # the route table makes this unreachable
            raise AccountError(404, "NOT_FOUND", "no such action")
    except operators.OperatorError as exc:
        raise _refuse(exc) from None
    return public(operators.people(state)[person_id]), ends
