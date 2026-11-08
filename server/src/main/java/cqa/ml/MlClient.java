package cqa.ml;

import cqa.dto.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;

/** One POST, no redirects/proxy/auth/retry. Deadline includes the complete bounded body. */
@Component
public class MlClient implements AutoCloseable {
    private final String configured;
    private final int deadline;
    private final ContractJson json;
    private final HttpClient client;
    public MlClient(ContractJson json, @Value("${cqa.ml-url:}") String configured,
            @Value("${cqa.ml-connect-timeout-ms:3000}") int connect,
            @Value("${cqa.ml-response-timeout-ms:70000}") int deadline) {
        this.json=json; this.configured=configured; this.deadline=Math.clamp(deadline,1,70000);
        client=HttpClient.newBuilder().connectTimeout(Duration.ofMillis(Math.clamp(connect,1,3000)))
            .version(HttpClient.Version.HTTP_1_1).followRedirects(HttpClient.Redirect.NEVER)
            .proxy(new ProxySelector() {
                @Override public List<Proxy> select(URI uri) { return List.of(Proxy.NO_PROXY); }
                @Override public void connectFailed(URI uri, SocketAddress address, IOException error) {}
            }).build();
    }
    public URI endpoint() {
        try {
            URI uri=new URI(configured);
            if (!"http".equals(uri.getScheme()) || !"127.0.0.1".equals(uri.getHost())
                    || uri.getPort()<1 || uri.getPort()>65535 || !"/v1/evaluate".equals(uri.getRawPath())
                    || uri.getRawUserInfo()!=null || uri.getRawQuery()!=null || uri.getRawFragment()!=null
                    || !uri.toASCIIString().equals(configured)) throw new URISyntaxException("", "invalid");
            return uri;
        } catch (URISyntaxException | IllegalArgumentException e) {
            throw new MlFailure(501,"EVALUATOR_UNCONFIGURED",false,false);
        }
    }
    public byte[] encode(EvaluationRequest request) {
        ContractValidation.request(request);
        byte[] bytes=json.write(request);
        if (bytes.length>ContractJson.REQUEST_LIMIT) throw new MlFailure(413,"PAYLOAD_TOO_LARGE",false,false);
        return bytes;
    }
    public record Health(boolean configured, boolean reachable, boolean ready, String reason,
            Integer admissionProtocol, String policyMode, String grantSha256, String provider, String model) {
        Health(boolean configured,boolean reachable,boolean ready,String reason) {
            this(configured,reachable,ready,reason,null,null,null,null,null);
        }
    }
    public static String admissionMismatch(Health health, String mode, SyntheticPolicy.Admission admission) {
        if (!admission.allowed()) return admission.reason();
        if (!health.configured() || !health.reachable()) return health.reason();
        if (!mode.equals("approved_dataset")) {
            if (health.policyMode()!=null && !mode.equals(health.policyMode())) return "PYTHON_POLICY_MISMATCH";
            return health.ready()?null:health.reason();
        }
        if (!Integer.valueOf(2).equals(health.admissionProtocol())) return "PYTHON_ADMISSION_UNSUPPORTED";
        if (!mode.equals(health.policyMode())) return "PYTHON_POLICY_MISMATCH";
        if (!SyntheticPolicy.PROVIDER.equals(health.provider()) || !SyntheticPolicy.MODEL.equals(health.model()))
            return "PYTHON_DESTINATION_MISMATCH";
        if (!health.ready()) return "PRIVACY_POLICY_UNCONFIGURED".equals(health.reason()) ? "PYTHON_ADMISSION_DENIED" : health.reason();
        if (!Objects.equals(admission.grantSha256(),health.grantSha256())) return "PYTHON_GRANT_MISMATCH";
        return null;
    }
    /** Configuration/readiness probe only: never sends conversation, rubric or a provider POST. */
    public Health health() {
        URI uri;
        try { uri = endpoint().resolve("/health"); }
        catch (MlFailure absent) { return new Health(false, false, false, absent.code); }
        var request = HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(3))
                .header("Accept", "application/json").GET().build();
        var future = client.sendAsync(request, info -> new LimitedBody(info));
        try {
            var response = future.get(3, TimeUnit.SECONDS);
            var value = json.parse(response.body(), 8192);
            if (!value.path("configured").isBoolean() || !value.path("ready").isBoolean()
                    || !"2.0.0".equals(value.path("contract_version").asText())) throw MlFailure.invalid();
            boolean ready = response.statusCode() == 200 && value.path("configured").booleanValue()
                    && value.path("ready").booleanValue() && value.path("reason").isNull();
            String reason = value.path("reason").asText("");
            if (!Set.of("EVALUATOR_UNCONFIGURED", "PRIVACY_POLICY_UNCONFIGURED", "EVALUATOR_BUSY").contains(reason))
                reason = "EVALUATOR_INVALID_OUTPUT";
            var protocol=value.path("admission_protocol");
            return new Health(true,true,ready,ready?null:reason,
                    protocol.isIntegralNumber()&&protocol.canConvertToInt()?protocol.intValue():null,
                    optionalText(value,"policy_mode"),optionalText(value,"grant_sha256"),
                    optionalText(value,"provider"),optionalText(value,"model"));
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt(); future.cancel(true);
        } catch (Exception e) { future.cancel(true); }
        return new Health(true, false, false, "EVALUATOR_BUSY");
    }
    private static String optionalText(com.fasterxml.jackson.databind.JsonNode value,String name) {
        return value.path(name).isTextual()?value.path(name).textValue():null;
    }
    public EvaluationResult evaluate(EvaluationRequest pinned, byte[] bytes) {
        return evaluate(pinned,bytes,false);
    }
    public EvaluationResult evaluate(EvaluationRequest pinned, byte[] bytes, boolean rubricConfirmed) {
        var builder=HttpRequest.newBuilder(endpoint()).timeout(Duration.ofMillis(deadline))
            .header("Content-Type","application/json; charset=utf-8").header("Accept","application/json")
            .header("Accept-Encoding","identity");
        if (rubricConfirmed) builder.header("X-CQA-Rubric-Confirmed","true");
        var request=builder.POST(HttpRequest.BodyPublishers.ofByteArray(bytes)).build();
        CompletableFuture<HttpResponse<byte[]>> future=client.sendAsync(request, info -> new LimitedBody(info));
        try {
            var response=future.get(deadline,TimeUnit.MILLISECONDS);
            if (response.statusCode()==200) return json.readResult(response.body(),pinned,ContractValidation.Mode.PRODUCTION);
            var error=json.readError(response.body(),response.statusCode(),pinned).detail();
            throw new MlFailure(response.statusCode(),error.code(),error.code().equals("EVALUATOR_TIMEOUT"),error.retryable());
        } catch (ContractViolation e) { throw MlFailure.invalid(); }
        catch (TimeoutException e) { future.cancel(true); throw MlFailure.timeout(); }
        catch (InterruptedException e) { future.cancel(true); Thread.currentThread().interrupt(); throw MlFailure.timeout(); }
        catch (ExecutionException e) {
            for (Throwable cause=e.getCause();cause!=null;cause=cause.getCause()) {
                if (cause instanceof MlFailure safe) throw safe;
                if (cause instanceof HttpTimeoutException) throw MlFailure.timeout();
                if (cause instanceof ConnectException) throw new MlFailure(503,"EVALUATOR_BUSY",false,true);
            }
            // A lost response is not proof that Python never received or billed the request.
            throw new MlFailure(502,"EVALUATOR_PROVIDER_ERROR",true,true);
        }
    }
    @Override public void close() { client.shutdownNow(); }
    private static final class LimitedBody implements HttpResponse.BodySubscriber<byte[]> {
        private final CompletableFuture<byte[]> result=new CompletableFuture<>();
        private final ByteArrayOutputStream bytes=new ByteArrayOutputStream();
        private Flow.Subscription subscription;
        LimitedBody(HttpResponse.ResponseInfo info) {
            String type=info.headers().firstValue("Content-Type").orElse("").toLowerCase(Locale.ROOT);
            if (info.statusCode()>=300 && info.statusCode()<400
                    || !type.matches("application/json(?:\\s*;\\s*charset=utf-8)?")
                    || !info.headers().firstValue("Content-Encoding").orElse("identity").equalsIgnoreCase("identity")
                    || info.headers().firstValueAsLong("Content-Length").orElse(0)>ContractJson.RESPONSE_LIMIT)
                result.completeExceptionally(MlFailure.invalid());
        }
        @Override public CompletionStage<byte[]> getBody() { return result; }
        @Override public void onSubscribe(Flow.Subscription value) {
            subscription=value; if(result.isDone())value.cancel(); else value.request(1);
        }
        @Override public void onNext(List<ByteBuffer> buffers) {
            if(result.isDone())return;
            for(var buffer:buffers) {
                if(buffer.remaining()>ContractJson.RESPONSE_LIMIT-bytes.size()) {
                    result.completeExceptionally(MlFailure.invalid());subscription.cancel();return;
                }
                byte[] part=new byte[buffer.remaining()];buffer.get(part);bytes.writeBytes(part);
            }
            subscription.request(1);
        }
        @Override public void onError(Throwable ignored) { result.completeExceptionally(new MlFailure(502,"EVALUATOR_PROVIDER_ERROR",true,true)); }
        @Override public void onComplete() { result.complete(bytes.toByteArray()); }
    }
}
