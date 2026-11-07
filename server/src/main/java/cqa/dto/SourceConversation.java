package cqa.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.List;

/** Immutable contract 2.0.0 value; wire names are intentionally unchanged. */
public record SourceConversation(
    @JsonProperty(value="id", required=true) @NotNull @Text String id,
    @JsonProperty(value="dataset_group_id", required=true) @NotNull @Text String dataset_group_id,
    @JsonProperty(value="conversation_id", required=true) @NotNull @Text String conversation_id,
    @JsonProperty(value="channel", required=true) @NotNull @Pattern(regexp="agent chat|voice call") String channel,
    @JsonProperty(value="language", required=true) @NotNull @Pattern(regexp="RU|KZ|EN") String language,
    @JsonProperty(value="messages", required=true) @NotNull @Size(min=1) List<@NotNull @Valid SourceMessage> messages
) {
    public SourceConversation {
        messages = messages == null ? null : List.copyOf(messages);
    }
}
