package org.socialrobotics.robotcontroller.core.concurrent;

/** Thread-safe owner of monotonically increasing operation generations. */
public final class GenerationRegistry {
    private final long[] generations = new long[GenerationGroup.values().length];
    private boolean closed;

    /** Starts a replacement generation and invalidates the prior generation in the group. */
    public synchronized GenerationToken begin(GenerationGroup group) {
        requireGroup(group);
        if (closed) {
            throw new IllegalStateException("generation registry is closed");
        }
        int index = group.ordinal();
        generations[index] = next(generations[index]);
        return new GenerationToken(this, group, generations[index], false);
    }

    /** Invalidates the current generation. Repeated cancellation remains safe. */
    public synchronized void cancel(GenerationGroup group) {
        requireGroup(group);
        if (!closed) {
            int index = group.ordinal();
            generations[index] = next(generations[index]);
        }
    }

    /** Permanently invalidates every current generation and rejects future starts. */
    public synchronized void invalidateAll() {
        if (closed) {
            return;
        }
        closed = true;
        for (int index = 0; index < generations.length; index++) {
            generations[index] = next(generations[index]);
        }
    }

    synchronized boolean isCurrent(GenerationGroup group, long generation) {
        return !closed && generations[group.ordinal()] == generation;
    }

    private static long next(long value) {
        if (value == Long.MAX_VALUE) {
            throw new IllegalStateException("generation counter exhausted");
        }
        return value + 1L;
    }

    private static void requireGroup(GenerationGroup group) {
        if (group == null) {
            throw new NullPointerException("group");
        }
    }
}
