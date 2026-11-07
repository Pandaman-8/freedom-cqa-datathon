package cqa.api;

import cqa.dataset.*;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping(value="/api/datasets", produces="application/json")
public class OrganizerController {
    private final RequestBodies bodies;
    private final OrganizerService organizer;
    public OrganizerController(RequestBodies bodies, OrganizerService organizer) { this.bodies = bodies; this.organizer = organizer; }
    @PostMapping(value="/fetch", consumes="application/json")
    public Dataset.ImportResult fetch(HttpServletRequest request) {
        return organizer.fetch(bodies.read(request, OrganizerService.FetchRequest.class));
    }
    @ExceptionHandler(OrganizerFailure.class)
    public ResponseEntity<OrganizerFailure.Body> failure(OrganizerFailure failure) {
        return ResponseEntity.status(failure.reason.status).body(failure.body());
    }
}
