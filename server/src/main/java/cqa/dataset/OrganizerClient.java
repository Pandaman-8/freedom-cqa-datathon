package cqa.dataset;

import cqa.api.RequestBodies;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import java.io.ByteArrayOutputStream;
import java.net.*;
import java.net.http.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import static cqa.dataset.OrganizerFailure.Reason.*;

/** One application-level GET; bounded whole-body deadline, memory and destinations. No logging. */
@Component
public class OrganizerClient implements AutoCloseable {
    private final String configuredUrl;
    private final int deadlineMillis;
    private final HttpClient client;
    public OrganizerClient(@Value("${cqa.organizer-url:}") String configuredUrl,
            @Value("${cqa.organizer-connect-timeout-ms:3000}") int connectMillis,
            @Value("${cqa.organizer-response-timeout-ms:10000}") int deadlineMillis) {
        this.configuredUrl = configuredUrl;
        // Engineering limits: configuration cannot create an unbounded network wait.
        this.deadlineMillis = Math.clamp(deadlineMillis, 1, 30000);
        client = HttpClient.newBuilder().connectTimeout(Duration.ofMillis(Math.clamp(connectMillis, 1, 5000)))
            .followRedirects(HttpClient.Redirect.NEVER).version(HttpClient.Version.HTTP_1_1).build();
    }
    static URI forGroup(String configured, String group) {
        if (configured == null || configured.isBlank()) throw new OrganizerFailure(UNCONFIGURED);
        try {
            URI uri = new URI(configured);
            if (!Set.of("http", "https").contains(uri.getScheme()) || uri.getHost() == null
                    || uri.getRawUserInfo() != null || uri.getRawFragment() != null
                    || uri.getPort() == 0 || uri.getPort() > 65535 || !uri.toASCIIString().equals(configured))
                throw new OrganizerFailure(CONFIGURATION_ERROR);
            String encoded = URLEncoder.encode(group, StandardCharsets.UTF_8).replace("+", "%20");
            String query = uri.getRawQuery();
            List<String> parts = new ArrayList<>();
            boolean replaced = false;
            if (query != null && !query.isEmpty()) for (String part : query.split("&", -1)) {
                String key = part.split("=", 2)[0];
                if (URLDecoder.decode(key, StandardCharsets.UTF_8).equals("group_id")) {
                    if (!replaced) parts.add(key + "=" + encoded);
                    replaced = true; // Collapse only duplicate group_id keys; preserve all other raw bytes.
                } else parts.add(part);
            }
            if (!replaced) parts.add("group_id=" + encoded);
            String prefix = configured.split("\\?", 2)[0];
            return new URI(prefix + "?" + String.join("&", parts));
        } catch (URISyntaxException | IllegalArgumentException e) {
            throw new OrganizerFailure(CONFIGURATION_ERROR); // Never carry URI/exceptions to logs or responses.
        }
    }
    public byte[] fetch(String group) {
        URI uri = forGroup(configuredUrl, group);
        var request = HttpRequest.newBuilder(uri).timeout(Duration.ofMillis(deadlineMillis))
            .header("Accept", "application/json").header("Accept-Encoding", "identity").GET().build();
        CompletableFuture<HttpResponse<byte[]>> future = client.sendAsync(request, info -> {
            OrganizerFailure failure = statusFailure(info.statusCode());
            if (failure == null && info.headers().firstValueAsLong("Content-Length").orElse(0) > RequestBodies.DATASET_LIMIT)
                failure = new OrganizerFailure(RESPONSE_TOO_LARGE);
            if (failure == null && !info.headers().firstValue("Content-Encoding").orElse("identity").equalsIgnoreCase("identity"))
                failure = new OrganizerFailure(INVALID_RESPONSE);
            return new LimitedBody(failure);
        });
        try {
            // Unlike an InputStream response, this future completes only after the entire bounded body.
            return future.get(deadlineMillis, TimeUnit.MILLISECONDS).body();
        } catch (TimeoutException e) {
            future.cancel(true); throw new OrganizerFailure(TIMEOUT);
        } catch (InterruptedException e) {
            future.cancel(true); Thread.currentThread().interrupt(); throw new OrganizerFailure(UNAVAILABLE);
        } catch (ExecutionException e) {
            for (Throwable cause = e.getCause(); cause != null; cause = cause.getCause()) {
                if (cause instanceof OrganizerFailure safe) throw safe;
                if (cause instanceof HttpTimeoutException) throw new OrganizerFailure(TIMEOUT);
            }
            throw new OrganizerFailure(UNAVAILABLE);
        }
    }
    private static OrganizerFailure statusFailure(int status) {
        if (status == 200) return null;
        return new OrganizerFailure(switch (status) {
            case 401, 403 -> ACCESS_DENIED;
            case 404 -> NOT_FOUND;
            case 429 -> RATE_LIMITED;
            default -> status >= 300 && status < 400 ? REDIRECT_REJECTED : UPSTREAM_ERROR;
        });
    }
    @Override public void close() { client.shutdownNow(); }

    /** Stops at limit+1 even with chunked, missing or misleading Content-Length. */
    private static final class LimitedBody implements HttpResponse.BodySubscriber<byte[]> {
        private final CompletableFuture<byte[]> result = new CompletableFuture<>();
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        private Flow.Subscription subscription;
        LimitedBody(OrganizerFailure failure) { if (failure != null) result.completeExceptionally(failure); }
        @Override public CompletionStage<byte[]> getBody() { return result; }
        @Override public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            if (result.isDone()) subscription.cancel(); else subscription.request(1);
        }
        @Override public void onNext(List<ByteBuffer> buffers) {
            if (result.isDone()) return;
            for (var buffer : buffers) {
                if (buffer.remaining() > RequestBodies.DATASET_LIMIT - bytes.size()) {
                    result.completeExceptionally(new OrganizerFailure(RESPONSE_TOO_LARGE)); subscription.cancel(); return;
                }
                byte[] chunk = new byte[buffer.remaining()]; buffer.get(chunk); bytes.writeBytes(chunk);
            }
            subscription.request(1);
        }
        @Override public void onError(Throwable ignored) { result.completeExceptionally(new OrganizerFailure(UNAVAILABLE)); }
        @Override public void onComplete() { result.complete(bytes.toByteArray()); }
    }
}
