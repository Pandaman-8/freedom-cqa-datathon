package cqa.dataset;

/** Java organizer API only: no changes to ML error codes or shared schemas. */
public final class OrganizerFailure extends RuntimeException {
    public enum Reason {
        UNCONFIGURED(503, "Organizer API is not configured on the Java server."),
        CONFIGURATION_ERROR(503, "Organizer API configuration is invalid."),
        ACCESS_DENIED(502, "Organizer API denied access. Check the server configuration or link expiry."),
        NOT_FOUND(404, "Organizer API did not find the requested dataset."),
        RATE_LIMITED(503, "Organizer API rate limit reached. Try again later."),
        REDIRECT_REJECTED(502, "Organizer API returned a redirect; no redirect was followed."),
        UPSTREAM_ERROR(502, "Organizer API returned an unsuccessful response."),
        UNAVAILABLE(503, "Organizer API is unavailable."),
        TIMEOUT(504, "Organizer API response deadline exceeded."),
        RESPONSE_TOO_LARGE(502, "Organizer API response exceeds the 16 MiB limit."),
        INVALID_RESPONSE(502, "Organizer API returned an invalid dataset."),
        GROUP_MISMATCH(502, "Organizer API returned a different dataset group.");
        public final int status;
        public final String message;
        Reason(int status, String message) { this.status = status; this.message = message; }
    }
    public final Reason reason;
    public OrganizerFailure(Reason reason) { super(reason.message); this.reason = reason; }
    public record Detail(String code, String message, boolean retryable, String request_id) {}
    public record Body(Detail detail) {}
    public Body body() { return new Body(new Detail("ORGANIZER_" + reason.name(), reason.message, false, null)); }
}
