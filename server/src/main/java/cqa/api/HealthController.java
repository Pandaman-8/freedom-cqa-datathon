package cqa.api;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {
    private final String version;

    public HealthController(@Value("${cqa.version}") String version) {
        this.version = version;
    }

    // Liveness of this Java application only, not ML or persistence readiness.
    @GetMapping(value = "/api/health", produces = MediaType.APPLICATION_JSON_VALUE)
    public HealthResponse health() {
        return new HealthResponse("ok", "freedom-cqa-java", version);
    }

    public record HealthResponse(String status, String service, String version) {}
}
