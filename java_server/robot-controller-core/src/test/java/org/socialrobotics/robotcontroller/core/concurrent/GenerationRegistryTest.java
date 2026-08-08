package org.socialrobotics.robotcontroller.core.concurrent;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class GenerationRegistryTest {
    @Test
    public void replacementInvalidatesPreviousGeneration() {
        GenerationRegistry registry = new GenerationRegistry();

        GenerationToken first = registry.begin(GenerationGroup.MOTION);
        GenerationToken second = registry.begin(GenerationGroup.MOTION);

        assertFalse(first.isValid());
        assertTrue(second.isValid());
    }

    @Test
    public void cancellationIsIdempotentAndDoesNotAffectOtherGroup() {
        GenerationRegistry registry = new GenerationRegistry();
        GenerationToken motion = registry.begin(GenerationGroup.MOTION);
        GenerationToken audio = registry.begin(GenerationGroup.AUDIO);

        registry.cancel(GenerationGroup.MOTION);
        registry.cancel(GenerationGroup.MOTION);

        assertFalse(motion.isValid());
        assertTrue(audio.isValid());
    }

    @Test
    public void shutdownInvalidatesEveryGeneration() {
        GenerationRegistry registry = new GenerationRegistry();
        GenerationToken motion = registry.begin(GenerationGroup.MOTION);
        GenerationToken audio = registry.begin(GenerationGroup.AUDIO);

        registry.invalidateAll();

        assertFalse(motion.isValid());
        assertFalse(audio.isValid());
    }
}
