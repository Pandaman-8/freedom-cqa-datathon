package cqa.dto;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Stream;
import static org.junit.jupiter.api.Assertions.*;

class ContractFixturesTest {
    static final Path ROOT = Path.of("..").toAbsolutePath().normalize();
    static final Path CONTRACTS = ROOT.resolve("contracts");
    static ContractJson codec;
    @BeforeAll static void start() { codec = new ContractJson(); }
    @AfterAll static void stop() { codec.close(); }

    static Stream<JsonNode> cases() throws Exception {
        JsonNode manifest = new ObjectMapper().readTree(CONTRACTS.resolve("fixtures/manifest.json").toFile());
        List<JsonNode> cases = new ArrayList<>();
        manifest.get("cases").forEach(cases::add);
        assertEquals(72, cases.size());
        return cases.stream();
    }

    @ParameterizedTest(name="shared fixture {index}") @MethodSource("cases")
    void publishedFixtureLayersAndDtoRoundTrip(JsonNode fixture) throws Exception {
        String id = fixture.get("id").asText();
        Boolean parsed = false, shape = null, context = null;
        JsonNode node = null;
        try {
            node = codec.parse(Files.readAllBytes(CONTRACTS.resolve(fixture.get("file").asText())), ContractJson.REQUEST_LIMIT);
            parsed = true;
        } catch (ContractViolation e) { assertEquals(ContractViolation.Layer.PARSE, e.layer(), id); }
        Object dto = null;
        if (parsed) {
            try {
                dto = codec.shape(node, type(fixture.get("schema").asText()));
                shape = true;
            } catch (ContractViolation e) { shape = false; assertEquals(ContractViolation.Layer.SHAPE, e.layer(), id); }
        }
        if (Boolean.TRUE.equals(shape)) {
            EvaluationRequest request = fixture.has("request") ? codec.read(
                Files.readAllBytes(CONTRACTS.resolve(fixture.get("request").asText())), EvaluationRequest.class) : null;
            try {
                switch (dto) {
                    case EvaluationRequest r -> ContractValidation.request(r);
                    case EvaluationResult r -> ContractValidation.result(request, r,
                        fixture.path("mode").asText().equals("production") ? ContractValidation.Mode.PRODUCTION : ContractValidation.Mode.OFFLINE_FIXTURE);
                    case ProviderOutput p -> ContractValidation.provider(request, p);
                    case ContractError e -> ContractValidation.error(e, fixture.get("http_status").asInt(), request);
                    default -> fail("Unrecognized fixture schema");
                }
                context = true;
            } catch (ContractViolation e) { context = false; assertEquals(ContractViolation.Layer.CONTEXT, e.layer(), id); }
        }
        assertEquals(nullableBoolean(fixture.get("expected").get("parse")), parsed, id + " parse");
        assertEquals(nullableBoolean(fixture.get("expected").get("schema")), shape, id + " shape");
        assertEquals(nullableBoolean(fixture.get("expected").get("context")), context, id + " context");
        if (Boolean.TRUE.equals(context)) {
            assertJsonEquivalent(node, codec.parse(codec.write(dto), ContractJson.REQUEST_LIMIT));
        }
    }

    static Class<?> type(String name) {
        return switch (name) {
            case "evaluation_request" -> EvaluationRequest.class;
            case "evaluation_result" -> EvaluationResult.class;
            case "provider_output" -> ProviderOutput.class;
            case "error" -> ContractError.class;
            default -> throw new IllegalArgumentException(name);
        };
    }
    private static Boolean nullableBoolean(JsonNode n) { return n.isNull() ? null : n.booleanValue(); }
    static void assertJsonEquivalent(JsonNode expected, JsonNode actual) {
        if (expected.isNumber()) {
            assertTrue(actual.isNumber());
            assertEquals(0, expected.decimalValue().compareTo(actual.decimalValue()));
        } else if (expected.isObject()) {
            assertEquals(expected.size(), actual.size());
            expected.properties().forEach(entry -> {
                assertTrue(actual.has(entry.getKey()), entry.getKey());
                assertJsonEquivalent(entry.getValue(), actual.get(entry.getKey()));
            });
        } else if (expected.isArray()) {
            assertEquals(expected.size(), actual.size());
            for (int i = 0; i < expected.size(); i++) assertJsonEquivalent(expected.get(i), actual.get(i));
        } else assertEquals(expected, actual);
    }
}
