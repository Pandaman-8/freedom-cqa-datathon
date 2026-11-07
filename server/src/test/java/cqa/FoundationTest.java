package cqa;

import cqa.api.HealthController.HealthResponse;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FoundationTest {
    @Autowired private TestRestTemplate http;
    @Autowired private ApplicationContext context;
    @Autowired private JdbcTemplate jdbc;

    @Test
    void applicationContextStartsWithSqliteDriver() {
        assertThat(context.getBean(Application.class)).isNotNull();
        assertThat(jdbc.queryForObject("SELECT 1", Integer.class)).isEqualTo(1);
    }

    @Test
    void healthReportsOnlyJavaLiveness() {
        var response = http.getForEntity("/api/health", HealthResponse.class);
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getHeaders().getContentType()).isNotNull()
                .satisfies(type -> assertThat(type.isCompatibleWith(MediaType.APPLICATION_JSON)).isTrue());
        assertThat(response.getBody()).isEqualTo(new HealthResponse("ok", "freedom-cqa-java", "0.1.0"));
    }

    @Test
    void indexIsServedAsHtml() {
        var response = http.getForEntity("/", String.class);
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getHeaders().getContentType()).isNotNull()
                .satisfies(type -> assertThat(type.isCompatibleWith(MediaType.TEXT_HTML)).isTrue());
        assertThat(response.getBody()).contains("Freedom CQA", "type=\"module\"", "src=\"/js/app.js\"");
    }

    @Test
    void staticAssetsAreAvailableWithoutFrontendBuild() {
        var css = http.getForEntity("/styles.css", String.class);
        var js = http.getForEntity("/js/app.js", String.class);
        assertThat(css.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(css.getHeaders().getContentType()).isNotNull()
                .satisfies(type -> assertThat(type.isCompatibleWith(MediaType.valueOf("text/css"))).isTrue());
        assertThat(css.getBody()).contains("@media");
        assertThat(js.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(js.getHeaders().getContentType().toString()).contains("javascript");
        assertThat(js.getBody()).contains("fetch('/api/health'");
    }
}
