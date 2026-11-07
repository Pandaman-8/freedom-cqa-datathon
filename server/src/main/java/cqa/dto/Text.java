package cqa.dto;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
import java.lang.annotation.*;

/** JSON Schema string length uses Unicode code points, not UTF-16 units. */
@Target({ElementType.FIELD, ElementType.PARAMETER, ElementType.RECORD_COMPONENT, ElementType.TYPE_USE})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = Text.Check.class)
public @interface Text {
    String message() default "invalid text";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
    int max() default Integer.MAX_VALUE;
    boolean nonblank() default true;

    class Check implements ConstraintValidator<Text, String> {
        private int max;
        private boolean nonblank;
        @Override public void initialize(Text rule) { max = rule.max(); nonblank = rule.nonblank(); }
        @Override public boolean isValid(String value, ConstraintValidatorContext context) {
            if (value == null) return true; // @NotNull owns nullability.
            int length = value.codePointCount(0, value.length());
            return length >= 1 && length <= max && (!nonblank || hasText(value));
        }
        /** Matches Python's Unicode whitespace policy used by the shared fixtures. */
        public static boolean hasText(String value) {
            return value != null && value.codePoints().anyMatch(c ->
                !Character.isWhitespace(c) && !Character.isSpaceChar(c) && c != 0x85);
        }
    }
}
