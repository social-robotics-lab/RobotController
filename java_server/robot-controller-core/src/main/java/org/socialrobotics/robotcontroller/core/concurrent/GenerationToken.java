package org.socialrobotics.robotcontroller.core.concurrent;

/** Immutable token rechecked immediately before a side-effecting operation executes. */
public final class GenerationToken {
    private static final GenerationToken ALWAYS_VALID =
            new GenerationToken(null, null, 0L, true);

    private final GenerationRegistry registry;
    private final GenerationGroup group;
    private final long generation;
    private final boolean alwaysValid;

    GenerationToken(
            GenerationRegistry registry,
            GenerationGroup group,
            long generation,
            boolean alwaysValid) {
        this.registry = registry;
        this.group = group;
        this.generation = generation;
        this.alwaysValid = alwaysValid;
    }

    /** Returns a token reserved for lifecycle work such as initialize and close. */
    public static GenerationToken alwaysValid() {
        return ALWAYS_VALID;
    }

    /** Returns whether this exact generation may still issue a side effect. */
    public boolean isValid() {
        return alwaysValid || registry.isCurrent(group, generation);
    }

    /** Returns the group-local monotonically increasing generation number. */
    public long generation() {
        return generation;
    }
}
