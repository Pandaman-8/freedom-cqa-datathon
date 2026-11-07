package cqa.api;

/** Only fixed safe messages; never carry user strings or JDBC causes. */
public final class ApiFailure extends RuntimeException {
    public final int status;
    public final String code;
    public ApiFailure(int status, String code, String message) {
        super(message); this.status = status; this.code = code;
    }
    public static ApiFailure invalid() { return new ApiFailure(422, "INVALID_INPUT", "Invalid request data."); }
    public static ApiFailure missing() { return new ApiFailure(404, "NOT_FOUND", "Resource not found."); }
    public static ApiFailure conflict() { return new ApiFailure(409, "VERSION_CONFLICT", "Stored data or version conflicts with this request."); }
    public static ApiFailure tooLarge() { return new ApiFailure(413, "PAYLOAD_TOO_LARGE", "Request body exceeds the allowed size."); }
    public static ApiFailure reviewConflict() { return new ApiFailure(409, "REVIEW_CONFLICT", "Review state conflicts with this request. Reload the evaluation."); }
    public static ApiFailure unsupportedScorer() { return new ApiFailure(409, "REVIEW_CONFLICT", "Stored scoring version is not supported. Review is unavailable."); }
}
