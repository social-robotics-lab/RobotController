package org.socialrobotics.robotcontroller.mock;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import org.socialrobotics.robotcontroller.core.backend.RobotBackend;
import org.socialrobotics.robotcontroller.core.backend.RobotBackendException;
import org.socialrobotics.robotcontroller.core.backend.RobotLifecycleState;
import org.socialrobotics.robotcontroller.core.backend.RobotPose;

/** Deterministic stateful robot fake with operation history and fault injection. */
public final class MockRobotBackend implements RobotBackend {
    private static final MockOperationHook NO_OPERATION_HOOK = new MockOperationHook() {
        @Override
        public void duringOperation(String operationName) {
        }
    };

    private final Object stateLock = new Object();
    private final MockOperationHook operationHook;
    private final List<String> operationHistory = new CopyOnWriteArrayList<String>();
    private final Map<String, RobotBackendException> failures =
            new ConcurrentHashMap<String, RobotBackendException>();
    private final Map<String, RobotBackendException> nextFailures =
            new ConcurrentHashMap<String, RobotBackendException>();
    private final AtomicInteger activeCalls = new AtomicInteger();
    private final AtomicInteger maximumConcurrentCalls = new AtomicInteger();
    private final Map<String, Integer> axes = new LinkedHashMap<String, Integer>();
    private final Map<String, Integer> ledValues = new LinkedHashMap<String, Integer>();
    private final List<LedWrite> ledWrites = new ArrayList<LedWrite>();
    private RobotLifecycleState lifecycleState = RobotLifecycleState.STARTING;
    private String ledOwnershipKey;
    private Set<String> ownedLedNames = Collections.emptySet();
    private boolean nativeMouthVoiceSyncEnabled = true;

    public MockRobotBackend() {
        this(NO_OPERATION_HOOK);
    }

    public MockRobotBackend(MockOperationHook operationHook) {
        if (operationHook == null) {
            throw new NullPointerException("operationHook");
        }
        this.operationHook = operationHook;
    }

    @Override
    public void initialize() throws RobotBackendException {
        perform("initialize", new Operation<Void>() {
            @Override
            public Void run() {
                synchronized (stateLock) {
                    lifecycleState = RobotLifecycleState.READY;
                }
                return null;
            }
        });
    }

    @Override
    public RobotLifecycleState lifecycleState() {
        synchronized (stateLock) {
            return lifecycleState;
        }
    }

    @Override
    public Map<String, Integer> readAxes() throws RobotBackendException {
        return perform("readAxes", new Operation<Map<String, Integer>>() {
            @Override
            public Map<String, Integer> run() {
                synchronized (stateLock) {
                    return immutableCopy(axes);
                }
            }
        });
    }

    @Override
    public void applyPose(final RobotPose pose) throws RobotBackendException {
        if (pose == null) {
            throw new NullPointerException("pose");
        }
        perform("applyPose", new Operation<Void>() {
            @Override
            public Void run() {
                synchronized (stateLock) {
                    axes.putAll(pose.axisDegrees());
                    ledValues.putAll(pose.ledValues());
                }
                return null;
            }
        });
    }

    @Override
    public void setLed(final String logicalLedName, final int value)
            throws RobotBackendException {
        if (logicalLedName == null) {
            throw new NullPointerException("logicalLedName");
        }
        perform("setLed", new Operation<Void>() {
            @Override
            public Void run() {
                synchronized (stateLock) {
                    ledValues.put(logicalLedName, value);
                    ledWrites.add(new LedWrite(
                            logicalLedName,
                            value,
                            Thread.currentThread().getName()));
                }
                return null;
            }
        });
    }

    @Override
    public boolean acquireLedOwnership(
            final String ownershipKey,
            final Set<String> logicalLedNames) throws RobotBackendException {
        requireOwnershipArguments(ownershipKey, logicalLedNames);
        return perform("acquireLedOwnership", new Operation<Boolean>() {
            @Override
            public Boolean run() {
                synchronized (stateLock) {
                    if (ledOwnershipKey != null && !ledOwnershipKey.equals(ownershipKey)) {
                        return Boolean.FALSE;
                    }
                    ledOwnershipKey = ownershipKey;
                    ownedLedNames = immutableSet(logicalLedNames);
                    return Boolean.TRUE;
                }
            }
        }).booleanValue();
    }

    @Override
    public void releaseLedOwnership(
            final String ownershipKey,
            final Set<String> logicalLedNames) throws RobotBackendException {
        requireOwnershipArguments(ownershipKey, logicalLedNames);
        perform("releaseLedOwnership", new Operation<Void>() {
            @Override
            public Void run() throws RobotBackendException {
                synchronized (stateLock) {
                    if (ledOwnershipKey == null) {
                        return null;
                    }
                    if (!ledOwnershipKey.equals(ownershipKey)
                            || !ownedLedNames.equals(logicalLedNames)) {
                        throw new RobotBackendException("LED ownership does not match");
                    }
                    ledOwnershipKey = null;
                    ownedLedNames = Collections.emptySet();
                    return null;
                }
            }
        });
    }

    @Override
    public void disableNativeMouthVoiceSync() throws RobotBackendException {
        perform("disableNativeMouthVoiceSync", new Operation<Void>() {
            @Override
            public Void run() {
                synchronized (stateLock) {
                    nativeMouthVoiceSyncEnabled = false;
                }
                return null;
            }
        });
    }

    @Override
    public void enableNativeMouthVoiceSync() throws RobotBackendException {
        perform("enableNativeMouthVoiceSync", new Operation<Void>() {
            @Override
            public Void run() {
                synchronized (stateLock) {
                    nativeMouthVoiceSyncEnabled = true;
                }
                return null;
            }
        });
    }

    @Override
    public void requestRobotStop() throws RobotBackendException {
        perform("requestRobotStop", new Operation<Void>() {
            @Override
            public Void run() {
                return null;
            }
        });
    }

    @Override
    public void close() throws RobotBackendException {
        perform("close", new Operation<Void>() {
            @Override
            public Void run() {
                synchronized (stateLock) {
                    lifecycleState = RobotLifecycleState.STOPPED;
                }
                return null;
            }
        });
    }

    public Map<String, Integer> currentLedValues() {
        synchronized (stateLock) {
            return immutableCopy(ledValues);
        }
    }

    /** Returns a side-effect-free snapshot for deterministic test assertions. */
    public Map<String, Integer> currentAxes() {
        synchronized (stateLock) {
            return immutableCopy(axes);
        }
    }

    public boolean nativeMouthVoiceSyncEnabled() {
        synchronized (stateLock) {
            return nativeMouthVoiceSyncEnabled;
        }
    }

    public String ledOwnershipKey() {
        synchronized (stateLock) {
            return ledOwnershipKey;
        }
    }

    public Set<String> ownedLedNames() {
        synchronized (stateLock) {
            return ownedLedNames;
        }
    }

    public List<String> operationHistory() {
        return Collections.unmodifiableList(new ArrayList<String>(operationHistory));
    }

    /** Returns written values for one logical LED in backend execution order. */
    public List<Integer> ledValueHistory(String logicalLedName) {
        if (logicalLedName == null) {
            throw new NullPointerException("logicalLedName");
        }
        synchronized (stateLock) {
            List<Integer> values = new ArrayList<Integer>();
            for (LedWrite write : ledWrites) {
                if (logicalLedName.equals(write.logicalLedName)) {
                    values.add(Integer.valueOf(write.value));
                }
            }
            return Collections.unmodifiableList(values);
        }
    }

    /** Returns thread names used for one logical LED, proving serialized dispatch in tests. */
    public List<String> ledWriteThreadHistory(String logicalLedName) {
        if (logicalLedName == null) {
            throw new NullPointerException("logicalLedName");
        }
        synchronized (stateLock) {
            List<String> names = new ArrayList<String>();
            for (LedWrite write : ledWrites) {
                if (logicalLedName.equals(write.logicalLedName)) {
                    names.add(write.threadName);
                }
            }
            return Collections.unmodifiableList(names);
        }
    }

    /** Seeds deterministic logical axes before a network integration test starts. */
    public void seedAxes(Map<String, Integer> initialAxes) {
        if (initialAxes == null || initialAxes.containsKey(null) || initialAxes.containsValue(null)) {
            throw new IllegalArgumentException("initialAxes must not contain nulls");
        }
        synchronized (stateLock) {
            axes.clear();
            axes.putAll(initialAxes);
        }
    }

    public int maximumConcurrentBackendCalls() {
        return maximumConcurrentCalls.get();
    }

    /** Causes the named operation to fail until the injection is cleared. */
    public void failOperation(String operationName, RobotBackendException failure) {
        if (operationName == null || failure == null) {
            throw new NullPointerException("operationName and failure are required");
        }
        failures.put(operationName, failure);
    }

    /** Causes exactly the next named operation to fail. */
    public void failNextOperation(String operationName, RobotBackendException failure) {
        if (operationName == null || failure == null) {
            throw new NullPointerException("operationName and failure are required");
        }
        nextFailures.put(operationName, failure);
    }

    public void clearFailure(String operationName) {
        failures.remove(operationName);
    }

    private <T> T perform(String operationName, Operation<T> operation)
            throws RobotBackendException {
        int active = activeCalls.incrementAndGet();
        updateMaximum(active);
        operationHistory.add(operationName);
        try {
            try {
                operationHook.duringOperation(operationName);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new RobotBackendException("Mock operation was interrupted", interrupted);
            }
            RobotBackendException failure = failures.get(operationName);
            if (failure != null) {
                throw failure;
            }
            RobotBackendException nextFailure = nextFailures.remove(operationName);
            if (nextFailure != null) {
                throw nextFailure;
            }
            return operation.run();
        } finally {
            activeCalls.decrementAndGet();
        }
    }

    private void updateMaximum(int candidate) {
        int observed = maximumConcurrentCalls.get();
        while (candidate > observed
                && !maximumConcurrentCalls.compareAndSet(observed, candidate)) {
            observed = maximumConcurrentCalls.get();
        }
    }

    private static void requireOwnershipArguments(String key, Set<String> names) {
        if (key == null || key.length() == 0) {
            throw new IllegalArgumentException("ownershipKey is required");
        }
        if (names == null || names.isEmpty() || names.contains(null)) {
            throw new IllegalArgumentException("logicalLedNames must be non-empty");
        }
    }

    private static Map<String, Integer> immutableCopy(Map<String, Integer> source) {
        return Collections.unmodifiableMap(new LinkedHashMap<String, Integer>(source));
    }

    private static Set<String> immutableSet(Set<String> source) {
        return Collections.unmodifiableSet(new LinkedHashSet<String>(source));
    }

    private interface Operation<T> {
        T run() throws RobotBackendException;
    }

    private static final class LedWrite {
        private final String logicalLedName;
        private final int value;
        private final String threadName;

        private LedWrite(String logicalLedName, int value, String threadName) {
            this.logicalLedName = logicalLedName;
            this.value = value;
            this.threadName = threadName;
        }
    }
}
