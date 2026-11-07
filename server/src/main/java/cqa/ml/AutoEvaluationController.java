package cqa.ml;

import cqa.api.*;
import cqa.dto.*;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping(value="/api",produces="application/json")
public class AutoEvaluationController {
    private final AutoEvaluationService service;
    private final RequestBodies bodies;
    public AutoEvaluationController(AutoEvaluationService service,RequestBodies bodies) {this.service=service;this.bodies=bodies;}
    @PostMapping(value="/evaluations/auto",consumes="application/json")
    public ResponseEntity<?> evaluate(HttpServletRequest request) {
        return service.evaluate(bodies.read(request,ApiModels.AutoRequest.class));
    }
    @GetMapping("/evaluation-requests/{id}")
    public RequestLedger.Status status(@PathVariable String id,HttpServletRequest request) {
        if(id.matches(ContractJson.UUID_PATTERN))request.setAttribute(RequestBodies.REQUEST_ID_ATTRIBUTE,id);
        return service.status(id);
    }
    @ExceptionHandler(MlFailure.class)
    public ResponseEntity<ContractError> failure(MlFailure failure,HttpServletRequest request) {
        return ResponseEntity.status(failure.status).body(new ContractError(failure.detail((String)request.getAttribute(RequestBodies.REQUEST_ID_ATTRIBUTE))));
    }
}
