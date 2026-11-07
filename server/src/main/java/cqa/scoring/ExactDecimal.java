package cqa.scoring;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

/** Exact ratio of decimals: even 1/3 is retained without intermediate rounding. */
record ExactDecimal(BigDecimal numerator, BigDecimal denominator) {
    static final ExactDecimal ZERO = of(BigDecimal.ZERO);
    ExactDecimal {
        if (denominator.signum() <= 0) throw new IllegalArgumentException("positive_denominator_required");
        int scale = Math.max(0, Math.max(numerator.scale(), denominator.scale()));
        BigInteger n = numerator.movePointRight(scale).toBigIntegerExact();
        BigInteger d = denominator.movePointRight(scale).toBigIntegerExact();
        BigInteger gcd = n.gcd(d);
        numerator = new BigDecimal(n.divide(gcd));
        denominator = new BigDecimal(d.divide(gcd));
    }
    static ExactDecimal of(BigDecimal value) { return new ExactDecimal(value, BigDecimal.ONE); }
    ExactDecimal add(ExactDecimal other) {
        return new ExactDecimal(numerator.multiply(other.denominator).add(other.numerator.multiply(denominator)),
            denominator.multiply(other.denominator));
    }
    ExactDecimal percentOf(BigDecimal weight) {
        return new ExactDecimal(numerator.multiply(BigDecimal.valueOf(100)), denominator.multiply(weight));
    }
    BigDecimal rounded() { return numerator.divide(denominator, 2, RoundingMode.HALF_UP); }
}
