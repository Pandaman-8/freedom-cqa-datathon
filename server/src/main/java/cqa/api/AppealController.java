package cqa.api;

import cqa.api.ApiModels.EvaluationView;
import cqa.review.ReviewModels.*;
import cqa.review.ReviewService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping(value="/api", produces="application/json")
public class AppealController {
    private final RequestBodies bodies;
    private final ReviewService reviews;
    public AppealController(RequestBodies bodies, ReviewService reviews) { this.bodies = bodies; this.reviews = reviews; }

    @PostMapping(value="/evaluations/{id}/appeals", consumes="application/json")
    @ResponseStatus(HttpStatus.CREATED)
    public AppealView create(@PathVariable String id, HttpServletRequest request) {
        return reviews.create(id, bodies.read(request, AppealRequest.class));
    }

    @PostMapping(value="/appeals/{id}/resolve", consumes="application/json")
    public EvaluationView resolve(@PathVariable String id,
            @RequestParam(name="expected_revision", required=false) String expected, HttpServletRequest request) {
        return reviews.resolve(id, RequestBodies.reviewRevision(expected), bodies.read(request, Resolution.class));
    }
}
