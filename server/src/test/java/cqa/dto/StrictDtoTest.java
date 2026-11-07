package cqa.dto;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import org.junit.jupiter.api.*;
import java.math.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Stream;
import static org.junit.jupiter.api.Assertions.*;

class StrictDtoTest {
    static final Path CONTRACTS = Path.of("../contracts");
    static ContractJson codec;
    static ObjectNode request;
    @BeforeAll static void start() throws Exception {
        codec = new ContractJson();
        request = (ObjectNode) codec.parse(Files.readAllBytes(CONTRACTS.resolve("fixtures/positive/evaluation_request.json")), ContractJson.REQUEST_LIMIT);
    }
    @AfterAll static void stop() { codec.close(); }

    @TestFactory Stream<DynamicTest> allRequiredFieldsUnknownFieldsAndScalarCoercions() throws Exception {
        List<DynamicTest> tests = new ArrayList<>();
        for (String name : List.of("evaluation_request", "evaluation_result", "provider_output", "error")) {
            ObjectNode original = (ObjectNode) codec.parse(Files.readAllBytes(CONTRACTS.resolve("fixtures/positive/" + name + ".json")), ContractJson.REQUEST_LIMIT);
            mutateFields(name, original, original, "", ContractFixturesTest.type(name), tests);
        }
        return tests.stream();
    }
    private void mutateFields(String name, ObjectNode root, JsonNode node, String pointer, Class<?> type, List<DynamicTest> tests) {
        if (node.isObject()) {
            ObjectNode unknown = root.deepCopy();
            ((ObjectNode) unknown.at(pointer)).put("unexpected", true);
            reject(tests, name + pointer + "/unknown", unknown, type);
            for (var entry : node.properties()) {
                String key = entry.getKey();
                ObjectNode missing = root.deepCopy();
                ((ObjectNode) missing.at(pointer)).remove(key);
                reject(tests, name + pointer + "/missing:" + key, missing, type);
                JsonNode value = entry.getValue();
                List<JsonNode> wrong = value.isNumber() ? List.of(TextNode.valueOf(value.asText()), BooleanNode.TRUE)
                    : value.isTextual() ? List.of(IntNode.valueOf(7), BooleanNode.TRUE)
                    : value.isBoolean() ? List.of(TextNode.valueOf(value.asText()), IntNode.valueOf(1))
                    : value.isArray() ? List.of(JsonNodeFactory.instance.objectNode())
                    : value.isObject() ? List.of(JsonNodeFactory.instance.arrayNode()) : List.of();
                for (int i = 0; i < wrong.size(); i++) {
                    ObjectNode bad = root.deepCopy(); ((ObjectNode) bad.at(pointer)).set(key, wrong.get(i));
                    reject(tests, name + pointer + "/type:" + key + ":" + i, bad, type);
                }
                mutateFields(name, root, value, pointer + "/" + key, type, tests);
            }
        } else if (node.isArray()) {
            for (int i = 0; i < node.size(); i++) mutateFields(name, root, node.get(i), pointer + "/" + i, type, tests);
        }
    }
    private void reject(List<DynamicTest> tests, String name, ObjectNode value, Class<?> type) {
        tests.add(DynamicTest.dynamicTest(name, () -> assertThrows(ContractViolation.class, () -> codec.shape(value, type))));
    }

    @Test void arbitraryPrecisionDecimalsAndIntegralTokensArePreserved() {
        ObjectNode tree = request.deepCopy();
        String value = "0.123456789012345678901234567890123456789";
        ((ObjectNode) tree.at("/checklist/criteria/0")).put("weight", new BigDecimal(value));
        ((ObjectNode) tree.get("checklist")).put("version", new BigDecimal("1208925819614629174706176.000"));
        var decoded = codec.read(tree.toString().getBytes(StandardCharsets.UTF_8), EvaluationRequest.class);
        assertEquals(0, new BigDecimal(value).compareTo(decoded.checklist().criteria().getFirst().weight()));
        assertEquals(new BigInteger("1208925819614629174706176"), decoded.checklist().version());
        ContractValidation.request(decoded);
    }
    @Test void fractionalIntegerAndBooleanStringAreRejected() {
        for (JsonNode invalid : List.of(DecimalNode.valueOf(new BigDecimal("2.1")), TextNode.valueOf("2"), BooleanNode.TRUE)) {
            ObjectNode tree = request.deepCopy(); ((ObjectNode) tree.get("checklist")).set("version", invalid);
            assertThrows(ContractViolation.class, () -> codec.shape(tree, EvaluationRequest.class));
        }
    }
    @Test void parserRejectsInvalidUtf8DuplicateNestedKeysNonfiniteOverflowAndTrailingText() {
        for (String invalid : List.of("{\"x\":{\"a\":1,\"a\":2}}", "{\"x\":NaN}", "{\"x\":Infinity}",
                "{\"x\":-Infinity}", "{\"x\":1e999}", "{} trailing", "{} {}", "")) {
            assertEquals(ContractViolation.Layer.PARSE, assertThrows(ContractViolation.class,
                () -> codec.parse(invalid.getBytes(StandardCharsets.UTF_8), 1024), invalid).layer());
        }
        assertThrows(ContractViolation.class, () -> codec.parse(new byte[]{(byte) 0xc3, 0x28}, 1024));
        assertThrows(ContractViolation.class, () -> codec.parse(new byte[1025], 1024));
        assertThrows(ContractViolation.class, () -> codec.read("null".getBytes(StandardCharsets.UTF_8), EvaluationRequest.class));
    }
    @Test void nullableFieldsAreRequiredButRemainNullOnRoundTrip() throws Exception {
        var error = codec.read(Files.readAllBytes(CONTRACTS.resolve("fixtures/positive/error_null_request_id.json")), ContractError.class);
        assertNull(error.detail().request_id());
        assertTrue(codec.parse(codec.write(error), 1024).get("detail").get("request_id").isNull());
    }
    @Test void unicodeWhitespaceAndCodePointLengthsMatchPublishedSchema() {
        for (String blank : List.of("", "\t\n", "\u00a0", "\u0085", "\u001c", "\u2007", "\u202f", "\u3000")) {
            assertThrows(ContractViolation.class, () -> codec.validateShape(new Evidence("m0001", blank)));
        }
        codec.validateShape(new Section("😀".repeat(40), "😀".repeat(180)));
        assertThrows(ContractViolation.class, () -> codec.validateShape(new Section("😀".repeat(41), "Title")));
        codec.validateShape(new Evidence("m0001", "\u200b")); // Zero-width space is not Python whitespace.
    }
    @Test void repeatedTimestampsRolesTextAndLongPositionalIdsArePreserved() {
        EvaluationRequest base = codec.shape(request, EvaluationRequest.class);
        List<SourceMessage> turns = new ArrayList<>();
        List<String> roles = List.of("client", "bot", "operator", "system");
        for (int i = 1; i <= 10001; i++) turns.add(new SourceMessage("m" + String.format(Locale.ROOT, "%04d", i),
            "00:00", roles.get((i - 1) % roles.size()), " Original e\u0301 text "));
        var conversation = new SourceConversation("SYNTHETIC:long", "SYNTHETIC", "long", "agent chat", "KZ", turns);
        var copy = new EvaluationRequest(base.contract_version(), base.request_id(), conversation, base.checklist());
        ContractValidation.request(copy);
        assertEquals("m10001", copy.conversation().messages().getLast().id());
        assertEquals(roles, copy.conversation().messages().subList(0, 4).stream().map(SourceMessage::speaker).toList());
        assertEquals(" Original e\u0301 text ", copy.conversation().messages().getLast().text());
        turns.clear(); assertEquals(10001, conversation.messages().size());
        assertThrows(UnsupportedOperationException.class, () -> conversation.messages().clear());
    }
    @Test void evidenceIsNeverTrimmedTranslatedOrUnicodeNormalized() throws Exception {
        var base = codec.shape(request, EvaluationRequest.class);
        var result = codec.read(Files.readAllBytes(CONTRACTS.resolve("fixtures/positive/evaluation_result.json")), EvaluationResult.class);
        CriterionAnswer original = result.answers().getFirst();
        String quote = original.evidence().getFirst().quote();
        for (String invalid : List.of(" " + quote + " ", quote.toUpperCase(Locale.ROOT), "Выдуманная цитата")) {
            var answers = new ArrayList<>(result.answers());
            answers.set(0, new CriterionAnswer(original.criterion_id(), original.answer(), original.value(), original.explanation(),
                List.of(new Evidence(original.evidence().getFirst().message_id(), invalid))));
            assertThrows(ContractViolation.class, () -> ContractValidation.groundedAnswers(base, answers));
        }
        ContractValidation.result(base, result, ContractValidation.Mode.OFFLINE_FIXTURE);
        assertThrows(ContractViolation.class, () -> ContractValidation.result(base, result, ContractValidation.Mode.PRODUCTION));
    }

    @Test void completeBoundaryMethodsEnforceContextAndKeepSafeErrors() throws Exception {
        byte[] requestBytes = Files.readAllBytes(CONTRACTS.resolve("fixtures/positive/evaluation_request.json"));
        EvaluationRequest pinned = codec.readRequest(requestBytes);
        codec.readResult(Files.readAllBytes(CONTRACTS.resolve("fixtures/positive/evaluation_result.json")), pinned, ContractValidation.Mode.OFFLINE_FIXTURE);
        codec.readProviderOutput(Files.readAllBytes(CONTRACTS.resolve("fixtures/positive/provider_output.json")), pinned);
        codec.readError(Files.readAllBytes(CONTRACTS.resolve("fixtures/positive/error.json")), 504, pinned);
        for (String invalid : List.of("result_wrong_request_id", "result_fabricated_quote")) {
            Path path = CONTRACTS.resolve("fixtures/negative/" + invalid + ".json");
            ContractViolation failure = assertThrows(ContractViolation.class, () -> codec.readResult(Files.readAllBytes(path), pinned, ContractValidation.Mode.OFFLINE_FIXTURE));
            assertEquals(ContractViolation.Layer.CONTEXT, failure.layer());
            assertNull(failure.getCause());
        }
        assertThrows(ContractViolation.class, () -> codec.readError(Files.readAllBytes(CONTRACTS.resolve("fixtures/positive/error.json")), 502, pinned));
    }
}
