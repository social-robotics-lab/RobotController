package org.socialrobotics.robotcontroller.app;

import java.nio.charset.StandardCharsets;
import java.util.Map;

/** Minimal deterministic UTF-8 encoder for the legacy read_axes JSON object. */
final class JsonObjectEncoder {
    private JsonObjectEncoder() {
    }

    static byte[] encodeIntegerMap(Map<String, Integer> values) {
        StringBuilder json = new StringBuilder();
        json.append('{');
        boolean first = true;
        for (Map.Entry<String, Integer> entry : values.entrySet()) {
            if (!first) {
                json.append(',');
            }
            first = false;
            appendString(json, entry.getKey());
            json.append(':').append(entry.getValue().intValue());
        }
        json.append('}');
        return json.toString().getBytes(StandardCharsets.UTF_8);
    }

    private static void appendString(StringBuilder target, String value) {
        target.append('"');
        for (int index = 0; index < value.length(); index++) {
            char current = value.charAt(index);
            switch (current) {
            case '"':
                target.append("\\\"");
                break;
            case '\\':
                target.append("\\\\");
                break;
            case '\b':
                target.append("\\b");
                break;
            case '\f':
                target.append("\\f");
                break;
            case '\n':
                target.append("\\n");
                break;
            case '\r':
                target.append("\\r");
                break;
            case '\t':
                target.append("\\t");
                break;
            default:
                if (current < 0x20) {
                    target.append(String.format("\\u%04x", Integer.valueOf(current)));
                } else {
                    target.append(current);
                }
            }
        }
        target.append('"');
    }
}
