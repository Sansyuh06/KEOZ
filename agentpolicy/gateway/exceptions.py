"""Custom exceptions and error codes for AgentPolicy Gateway."""

class PolicyException(Exception):
    """Base exception for policy engine."""
    def __init__(self, message: str, code: str = "POLICY_ERROR", status_code: int = 400, details: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class PolicyViolation(PolicyException):
    """Raised when an action violates a hard merchant policy constraint."""
    def __init__(self, message: str, code: str = "POLICY_VIOLATION", details: dict = None):
        super().__init__(message, code=code, status_code=403, details=details)


class AgentIdentityError(PolicyException):
    """Raised when agent identity authentication or commitment limit fails."""
    def __init__(self, message: str, code: str = "AGENT_IDENTITY_ERROR", details: dict = None):
        super().__init__(message, code=code, status_code=401, details=details)


class MarginFloorViolation(PolicyException):
    """Raised when composed deal parameters violate overall merchant margin."""
    def __init__(self, message: str, code: str = "MARGIN_FLOOR_VIOLATION", details: dict = None):
        super().__init__(message, code=code, status_code=403, details=details)


class PendingApproval(PolicyException):
    """Raised/Returned when a transaction requires async human signoff."""
    def __init__(self, message: str, approval_url: str, reason: str, approval_id: str):
        super().__init__(message, code="REQUIRES_HUMAN_APPROVAL", status_code=202, details={
            "approval_url": approval_url,
            "reason": reason,
            "approval_id": approval_id
        })
        self.approval_url = approval_url
        self.reason = reason
        self.approval_id = approval_id
