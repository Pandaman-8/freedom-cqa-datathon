package cqa.dto;

import com.fasterxml.jackson.core.*;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.cfg.CoercionAction;
import com.fasterxml.jackson.databind.cfg.CoercionInputShape;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.databind.module.SimpleModule;
import com.fasterxml.jackson.databind.type.LogicalType;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

/** Explicit boundary codec; no global change to the T03 Spring ObjectMapper. */
public final class ContractJson implements AutoCloseable {
    public static final String UUID_PATTERN = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
    public static final int REQUEST_LIMIT = 1024 * 1024;
    public static final int RESPONSE_LIMIT = 256 * 1024;
    // IEEE overflow threshold, expressed exactly without binary floating arithmetic.
    private static final BigDecimal FLOAT_OVERFLOW = new BigDecimal(
        BigInteger.ONE.shiftLeft(1024).subtract(BigInteger.ONE.shiftLeft(970)));
    private final ObjectMapper mapper;
    private final ValidatorFactory factory = Validation.buildDefaultValidatorFactory();
    private final Validator validator = factory.getValidator();

    public ContractJson() {
        mapper = JsonMapper.builder(JsonFactory.builder()
                .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION).build())
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .enable(DeserializationFeature.FAIL_ON_IGNORED_PROPERTIES)
            .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
            .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
            .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
            .enable(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS)
            .disable(MapperFeature.ALLOW_COERCION_OF_SCALARS).build();
        for (LogicalType type : new LogicalType[]{LogicalType.Textual, LogicalType.Boolean}) {
            for (CoercionInputShape shape : new CoercionInputShape[]{CoercionInputShape.Integer,
                    CoercionInputShape.Float, CoercionInputShape.Boolean, CoercionInputShape.String,
                    CoercionInputShape.EmptyString}) {
                // Exact native types are unaffected by coercion rules.
                mapper.coercionConfigFor(type).setCoercion(shape, CoercionAction.Fail);
            }
        }
        SimpleModule numbers = new SimpleModule();
        numbers.addDeserializer(BigDecimal.class, new JsonDeserializer<>() {
            @Override public BigDecimal deserialize(JsonParser p, DeserializationContext c) throws IOException {
                if (!p.currentToken().isNumeric()) throw new IOException("number_required");
                return p.getDecimalValue();
            }
        });
        numbers.addDeserializer(BigInteger.class, new JsonDeserializer<>() {
            @Override public BigInteger deserialize(JsonParser p, DeserializationContext c) throws IOException {
                if (!p.currentToken().isNumeric()) throw new IOException("integer_required");
                try { return p.getDecimalValue().toBigIntegerExact(); }
                catch (ArithmeticException e) { throw new IOException("integer_required"); }
            }
        });
        mapper.registerModule(numbers);
    }

    public JsonNode parse(byte[] bytes, int limit) {
        if (bytes == null || bytes.length > limit) throw parseFailure("payload_limit");
        try {
            String json = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();
            // Scan before tree construction so numeric overflow remains a parser-layer failure.
            try (JsonParser parser = mapper.createParser(json)) {
                while (parser.nextToken() != null) {
                    if (parser.currentToken() == JsonToken.VALUE_NUMBER_FLOAT
                            && parser.getDecimalValue().abs().compareTo(FLOAT_OVERFLOW) >= 0) {
                        throw parseFailure("numeric_overflow");
                    }
                }
            }
            JsonNode node = mapper.readTree(json);
            if (node == null || node.isMissingNode()) throw parseFailure("empty_json");
            return node;
        } catch (IOException | ArithmeticException e) { throw parseFailure("invalid_json"); }
    }

    /** Shape only; context checks require the pinned request and are explicit below. */
    public <T> T shape(JsonNode node, Class<T> type) {
        try {
            T result = mapper.treeToValue(node, type);
            validateShape(result);
            return result;
        } catch (IOException | IllegalArgumentException e) {
            throw new ContractViolation(ContractViolation.Layer.SHAPE, "invalid_dto");
        }
    }

    public <T> T read(byte[] bytes, Class<T> type) {
        return shape(parse(bytes, type == EvaluationRequest.class ? REQUEST_LIMIT : RESPONSE_LIMIT), type);
    }

    /** Complete validation entry points for future adapters; no I/O or HTTP here. */
    public EvaluationRequest readRequest(byte[] bytes) {
        EvaluationRequest request = read(bytes, EvaluationRequest.class);
        ContractValidation.request(request);
        return request;
    }

    public EvaluationResult readResult(byte[] bytes, EvaluationRequest pinned, ContractValidation.Mode mode) {
        EvaluationResult result = read(bytes, EvaluationResult.class);
        ContractValidation.result(pinned, result, mode);
        return result;
    }

    public ProviderOutput readProviderOutput(byte[] bytes, EvaluationRequest pinned) {
        ProviderOutput output = read(bytes, ProviderOutput.class);
        ContractValidation.provider(pinned, output);
        return output;
    }

    public ContractError readError(byte[] bytes, int httpStatus, EvaluationRequest pinned) {
        ContractError error = read(bytes, ContractError.class);
        ContractValidation.error(error, httpStatus, pinned);
        return error;
    }

    public void validateShape(Object dto) {
        if (dto == null || !validator.validate(dto).isEmpty())
            throw new ContractViolation(ContractViolation.Layer.SHAPE, "invalid_dto");
    }

    /** For outbound DTOs; caller still supplies context validation before transmission. */
    public byte[] write(Object dto) {
        validateShape(dto);
        try { return mapper.writeValueAsBytes(dto); }
        catch (IOException e) { throw new ContractViolation(ContractViolation.Layer.SHAPE, "invalid_dto"); }
    }

    private static ContractViolation parseFailure(String rule) {
        return new ContractViolation(ContractViolation.Layer.PARSE, rule);
    }
    @Override public void close() { factory.close(); }
}
