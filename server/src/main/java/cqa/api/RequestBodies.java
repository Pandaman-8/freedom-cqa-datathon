package cqa.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import cqa.dataset.Dataset;
import cqa.dto.ContractJson;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.stereotype.Component;
import java.io.IOException;
import java.math.BigInteger;

@Component
public class RequestBodies {
    public static final int DATASET_LIMIT = 16 * 1024 * 1024;
    public static final String REQUEST_ID_ATTRIBUTE = RequestBodies.class.getName() + ".requestId";
    private final ContractJson json;
    public RequestBodies(ContractJson json) { this.json = json; }
    public <T> T read(HttpServletRequest request, Class<T> type) {
        int limit = type == Dataset.Envelope.class ? DATASET_LIMIT : ContractJson.REQUEST_LIMIT;
        // Bound actual bytes, including chunked requests. Reading this bounded prefix
        // also avoids an early response resetting uploads just over the limit.
        byte[] bytes = readBytes(request, limit);
        JsonNode node = json.parse(bytes, limit);
        if (type == ApiModels.AutoRequest.class && node.path("request_id").isTextual()
                && node.get("request_id").textValue().matches(ContractJson.UUID_PATTERN))
            request.setAttribute(REQUEST_ID_ATTRIBUTE, node.get("request_id").textValue());
        return shapeWithDefaults(node, type);
    }
    public byte[] readBytes(HttpServletRequest request, int limit) {
        try {
            byte[] bytes = request.getInputStream().readNBytes(limit + 1);
            if (bytes.length > limit) throw ApiFailure.tooLarge();
            return bytes;
        } catch (IOException e) { throw ApiFailure.invalid(); }
    }
    /** Upload and organizer fetch use the same bounded parser and legacy optional defaults. */
    public Dataset.Envelope dataset(byte[] bytes) {
        return shapeWithDefaults(json.parse(bytes, DATASET_LIMIT), Dataset.Envelope.class);
    }
    private <T> T shapeWithDefaults(JsonNode node, Class<T> type) {
        // Preserve legacy optional defaults only; never coerce values or discard unknown fields.
        if (node instanceof ObjectNode object) {
            if (type == Dataset.Envelope.class) {
                if (!object.has("error")) object.put("error", "");
                for (JsonNode record : object.path("data").path("records")) {
                    if (record instanceof ObjectNode item && !item.has("audio_url")) item.putNull("audio_url");
                }
            } else if (type == ApiModels.ChecklistDraft.class && !object.has("description")) object.put("description", "");
            else if (type == cqa.review.ReviewModels.Resolution.class && !object.has("replacement")) object.putNull("replacement");
        }
        return json.shape(node, type);
    }
    public static BigInteger version(String value, boolean required) {
        if (value == null && !required) return null;
        if (value == null || !value.matches("[0-9]+")) throw ApiFailure.invalid();
        BigInteger version = new BigInteger(value);
        if (version.signum() <= 0) throw ApiFailure.invalid();
        return version;
    }
    public static long reviewRevision(String value) {
        if (value == null || !value.matches("[0-9]{1,19}")) throw ApiFailure.invalid();
        try { return Long.parseLong(value); }
        catch (NumberFormatException e) { throw ApiFailure.invalid(); }
    }
}
