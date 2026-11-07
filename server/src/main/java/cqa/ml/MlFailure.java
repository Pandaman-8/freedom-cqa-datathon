package cqa.ml;

import cqa.dto.ErrorDetail;

/** Fixed messages only: never retain a transport exception, URI or upstream message. */
public final class MlFailure extends RuntimeException {
    public final int status;
    public final String code;
    public final boolean unknown, retryable;
    public MlFailure(int status, String code, boolean unknown, boolean retryable) {
        super(switch (code) {
            case "EVALUATOR_UNCONFIGURED" -> "Local ML endpoint is not configured correctly.";
            case "PRIVACY_POLICY_UNCONFIGURED" -> "Only the bundled, verified synthetic fixture context is permitted.";
            case "EVALUATOR_TIMEOUT" -> "Evaluation outcome is unknown. Check request status before an explicit new attempt.";
            case "REQUEST_ID_CONFLICT" -> "Request ID belongs to a different evaluation payload.";
            case "PAYLOAD_TOO_LARGE" -> "Evaluation request exceeds the allowed size.";
            case "EVALUATOR_INVALID_OUTPUT" -> "ML response failed strict validation. No evaluation was saved.";
            default -> "ML evaluation did not complete successfully. Check request status before retrying.";
        });
        this.status=status; this.code=code; this.unknown=unknown; this.retryable=retryable;
    }
    public ErrorDetail detail(String id) { return new ErrorDetail(code, getMessage(), retryable, id); }
    public static MlFailure invalid() { return new MlFailure(502,"EVALUATOR_INVALID_OUTPUT",false,false); }
    public static MlFailure timeout() { return new MlFailure(504,"EVALUATOR_TIMEOUT",true,true); }
}
