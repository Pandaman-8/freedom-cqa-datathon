package cqa.dto;

/** Safe rule identifiers only: never retain payloads or parser exception messages. */
public final class ContractViolation extends IllegalArgumentException {
    public enum Layer { PARSE, SHAPE, CONTEXT }
    private final Layer layer;
    public ContractViolation(Layer layer, String rule) { super(rule); this.layer = layer; }
    public Layer layer() { return layer; }
}
