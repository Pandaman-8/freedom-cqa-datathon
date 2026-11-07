package cqa.dataset;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import static org.junit.jupiter.api.Assertions.*;

class OrganizerUriTest {
    @Test void appendAndReplacePreserveUnrelatedRawQueryAndPath() {
        assertEquals("https://example.invalid/a%2Fb?group_id=DEV", OrganizerClient.forGroup("https://example.invalid/a%2Fb", "DEV").toString());
        assertEquals("https://example.invalid/?sig=a%2fb+%3D&%67roup_id=CONTROL&&sv=x&sp=", OrganizerClient.forGroup(
            "https://example.invalid/?sig=a%2fb+%3D&%67roup_id=DEV&&group_id=OLD&sv=x&sp=", "CONTROL").toString());
        assertEquals("https://example.invalid/?sig=raw&group_id=DEV", OrganizerClient.forGroup("https://example.invalid/?sig=raw", "DEV").toString());
    }
    @ParameterizedTest @ValueSource(strings={"file:///tmp/private", "https://user:secret@example.invalid/", "https://example.invalid/#fragment", "not a URL", "https://example.invalid/%invalid", "https://example.invalid:99999/", "http://example.invalid:0/", "relative/path", "//example.invalid/path", "/relative/path"})
    void unsafeOrMalformedConfiguredAddressIsRejectedWithoutEcho(String value) {
        var failure = assertThrows(OrganizerFailure.class, () -> OrganizerClient.forGroup(value, "DEV"));
        assertEquals(OrganizerFailure.Reason.CONFIGURATION_ERROR, failure.reason); assertFalse(failure.getMessage().contains(value));
    }
}
