package cqa.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.List;

/** Immutable contract 2.0.0 value; wire names are intentionally unchanged. */
public record Diagnostics(
    @JsonProperty(value="provider", required=true) @NotNull @Text String provider,
    @JsonProperty(value="model", required=true) @NotNull @Text String model,
    @JsonProperty(value="prompt_version", required=true) @NotNull @Text String prompt_version,
    @JsonProperty(value="attempt_count", required=true) @NotNull @DecimalMin("0") @DecimalMax("2") BigInteger attempt_count,
    @JsonProperty(value="input_tokens", required=true) @DecimalMin("0") BigInteger input_tokens,
    @JsonProperty(value="output_tokens", required=true) @DecimalMin("0") BigInteger output_tokens,
    @JsonProperty(value="estimated_cost_usd", required=true) @DecimalMin("0") BigDecimal estimated_cost_usd,
    @JsonProperty(value="latency_ms", required=true) @DecimalMin("0") BigInteger latency_ms,
    @JsonProperty(value="warnings", required=true) @NotNull List<@NotNull @Pattern(regexp="DOMAIN_FACT_UNVERIFIED|TRANSCRIPTION_AMBIGUOUS|AUDIO_NOT_ASSESSED|MODEL_UNCERTAINTY") String> warnings
) {
    public Diagnostics {
        warnings = warnings == null ? null : List.copyOf(warnings);
    }
    @AssertTrue @JsonIgnore
    public boolean isWarningsUnique() {
        return warnings == null || warnings.stream().distinct().count() == warnings.size();
    }
}
