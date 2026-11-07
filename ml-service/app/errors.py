from .validation import STATUS_CODES

MESSAGES = {
    "INVALID_INPUT": "Request does not satisfy the evaluation contract or contains no assessable text.",
    "INPUT_TOO_LARGE": "Input exceeds the provider context capacity. No text was truncated.",
    "UNSUPPORTED_CONTRACT": "Only contract 2.0.0 is supported.",
    "PAYLOAD_TOO_LARGE": "Request exceeds the 1 MiB byte limit.",
    "EVALUATOR_UNCONFIGURED": "Configure a Groq key, supported model and confirmed Free Plan first.",
    "PRIVACY_POLICY_UNCONFIGURED": "Only registered own synthetic conversations are authorized.",
    "EVALUATOR_INVALID_OUTPUT": "Model output failed strict structure or evidence validation.",
    "EVALUATOR_PROVIDER_ERROR": "The inference provider could not complete the evaluation.",
    "EVALUATOR_RATE_LIMITED": "Provider rate limit reached. Check request status before retrying.",
    "EVALUATOR_AUTH": "Provider credentials or model permissions were rejected.",
    "EVALUATOR_BUSY": "An evaluation is already running. Check request status before retrying.",
    "EVALUATOR_TIMEOUT": "Evaluation deadline exceeded. Check request status before retrying.",
}


class ServiceError(Exception):
    def __init__(self, code, *, retryable=False, retry_after=None, diagnostic=None):
        super().__init__(code)
        self.code = code
        self.status = next(status for status, codes in STATUS_CODES.items() if code in codes)
        self.retryable = retryable
        self.retry_after = retry_after
        self.diagnostic = diagnostic  # Local only: never added to the contract envelope.

    def envelope(self, request_id):
        return {"detail": {"code": self.code, "message": MESSAGES[self.code],
                           "retryable": self.retryable, "request_id": request_id}}
