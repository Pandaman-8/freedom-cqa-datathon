package cqa.dataset;

import com.fasterxml.jackson.annotation.JsonProperty;
import cqa.dto.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigInteger;
import java.util.*;

/** Organizer import shape; separate from the smaller, audio-free ML projection. */
public final class Dataset {
    private Dataset() {}
    public record Envelope(
        @JsonProperty(required=true) @NotNull String error,
        @JsonProperty(required=true) @NotNull Boolean isSuccess,
        @JsonProperty(required=true) @NotNull @Valid Data data) {}
    public record Data(
        @JsonProperty(required=true) @NotNull @Text String dataset_group_id,
        @JsonProperty(required=true) @NotNull @DecimalMin("0") BigInteger total_records,
        @JsonProperty(required=true) @NotNull List<@NotNull @Valid Record> records) {
        public Data { records = records == null ? null : List.copyOf(records); }
    }
    public record Turn(
        @JsonProperty(required=true) @NotNull @Text String timestamp,
        @JsonProperty(required=true) @NotNull @Pattern(regexp="operator|client|bot|system") String speaker,
        @JsonProperty(required=true) @NotNull String text) {}
    public record Record(
        @JsonProperty(required=true) @NotNull @Text String conversation_id,
        @JsonProperty(required=true) @NotNull @Pattern(regexp="agent chat|voice call") String channel,
        @JsonProperty(required=true) @NotNull @Pattern(regexp="RU|KZ|EN") String language,
        @JsonProperty(required=true) @NotNull @Size(min=1) List<@NotNull @Valid Turn> transcript,
        @JsonProperty(required=true) String audio_url) {
        public Record { transcript = transcript == null ? null : List.copyOf(transcript); }
        public List<SourceMessage> messages() {
            List<SourceMessage> result = new ArrayList<>();
            for (int i = 0; i < transcript.size(); i++) {
                Turn t = transcript.get(i);
                result.add(new SourceMessage("m" + String.format(Locale.ROOT, "%04d", i + 1), t.timestamp(), t.speaker(), t.text()));
            }
            return List.copyOf(result);
        }
    }
    public record Summary(String id, String conversation_id, String dataset_group_id, String language,
        String channel, int message_count, String imported_at) {}
    public record Conversation(String id, String conversation_id, String dataset_group_id, String language,
        String channel, int message_count, String imported_at, List<Turn> transcript,
        List<SourceMessage> messages, String audio_url) {
        public SourceConversation projection() { return new SourceConversation(id, dataset_group_id, conversation_id, channel, language, messages); }
    }
    public record ImportResult(String dataset_group_id, int imported_records, Map<String,Integer> languages, Map<String,Integer> channels) {}
}
