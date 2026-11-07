package cqa.repository;

import cqa.dto.ContractJson;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.cfg.JsonNodeFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import org.springframework.stereotype.Component;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

@Component
public class StoredJson {
    private final ContractJson json;
    private final JsonMapper stored = JsonMapper.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
        .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
        .enable(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS)
        .disable(JsonNodeFeature.STRIP_TRAILING_BIGDECIMAL_ZEROES).build();
    public StoredJson(ContractJson json) { this.json = json; }
    public String write(Object value) { return new String(json.write(value), StandardCharsets.UTF_8); }
    public <T> T read(String value, Class<T> type) {
        // Own persisted JSON is not an ML response (256 KiB). Preserve decimal scale
        // of the saved snapshot as well as its value; apply the same strict DTO binding.
        try { return json.shape(stored.readTree(value), type); }
        catch (IOException e) { throw new IllegalStateException("Invalid stored JSON"); }
    }
}
