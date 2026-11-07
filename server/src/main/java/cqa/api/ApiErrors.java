package cqa.api;

import cqa.dto.*;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

@RestControllerAdvice
public class ApiErrors {
    @ExceptionHandler(ApiFailure.class)
    public ResponseEntity<ContractError> failure(ApiFailure failure, HttpServletRequest request) {
        String id = (String) request.getAttribute(RequestBodies.REQUEST_ID_ATTRIBUTE);
        return ResponseEntity.status(failure.status).body(new ContractError(new ErrorDetail(failure.code, failure.getMessage(), false, id)));
    }
    @ExceptionHandler({ContractViolation.class, HttpMediaTypeNotSupportedException.class, HttpRequestMethodNotSupportedException.class})
    public ResponseEntity<ContractError> invalid(Exception ignored, HttpServletRequest request) { return failure(ApiFailure.invalid(), request); }
    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<ContractError> missing(Exception ignored, HttpServletRequest request) { return failure(ApiFailure.missing(), request); }
    @ExceptionHandler(Exception.class)
    public ResponseEntity<Void> unexpected(Exception ignored) {
        // No new shared error code: unexpected 500 has no body, payload or SQL details.
        return ResponseEntity.internalServerError().build();
    }
}
