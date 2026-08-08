package org.socialrobotics.robotcontroller.core.command;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Small dependency-free RFC 8259 parser with duplicate-key and depth rejection. */
final class StrictJsonParser {
    private static final int MAXIMUM_DEPTH = 64;

    private final String text;
    private int offset;

    private StrictJsonParser(String text) {
        this.text = text;
    }

    static Object parse(String text) throws CommandValidationException {
        if (text == null) {
            throw new NullPointerException("text");
        }
        StrictJsonParser parser = new StrictJsonParser(text);
        Object result = parser.readValue(0);
        parser.skipWhitespace();
        if (parser.offset != text.length()) {
            parser.fail("trailing data after JSON value");
        }
        return result;
    }

    private Object readValue(int depth) throws CommandValidationException {
        if (depth > MAXIMUM_DEPTH) {
            fail("JSON nesting exceeds maximum depth");
        }
        skipWhitespace();
        if (offset >= text.length()) {
            fail("unexpected end of JSON");
        }
        char current = text.charAt(offset);
        if (current == '{') {
            return readObject(depth + 1);
        }
        if (current == '[') {
            return readArray(depth + 1);
        }
        if (current == '"') {
            return readString();
        }
        if (current == 't') {
            readLiteral("true");
            return Boolean.TRUE;
        }
        if (current == 'f') {
            readLiteral("false");
            return Boolean.FALSE;
        }
        if (current == 'n') {
            readLiteral("null");
            return null;
        }
        if (current == '-' || isDigit(current)) {
            return readNumber();
        }
        fail("invalid JSON token");
        return null;
    }

    private Map<String, Object> readObject(int depth) throws CommandValidationException {
        offset++;
        Map<String, Object> result = new LinkedHashMap<String, Object>();
        skipWhitespace();
        if (consume('}')) {
            return result;
        }
        while (true) {
            skipWhitespace();
            if (offset >= text.length() || text.charAt(offset) != '"') {
                fail("object member name must be a string");
            }
            String name = readString();
            if (result.containsKey(name)) {
                fail("duplicate object member");
            }
            skipWhitespace();
            require(':');
            result.put(name, readValue(depth));
            skipWhitespace();
            if (consume('}')) {
                return result;
            }
            require(',');
        }
    }

    private List<Object> readArray(int depth) throws CommandValidationException {
        offset++;
        List<Object> result = new ArrayList<Object>();
        skipWhitespace();
        if (consume(']')) {
            return result;
        }
        while (true) {
            result.add(readValue(depth));
            skipWhitespace();
            if (consume(']')) {
                return result;
            }
            require(',');
        }
    }

    private String readString() throws CommandValidationException {
        require('"');
        StringBuilder result = new StringBuilder();
        while (offset < text.length()) {
            char current = text.charAt(offset++);
            if (current == '"') {
                validateSurrogates(result);
                return result.toString();
            }
            if (current == '\\') {
                if (offset >= text.length()) {
                    fail("truncated JSON escape");
                }
                char escaped = text.charAt(offset++);
                switch (escaped) {
                case '"':
                case '\\':
                case '/':
                    result.append(escaped);
                    break;
                case 'b':
                    result.append('\b');
                    break;
                case 'f':
                    result.append('\f');
                    break;
                case 'n':
                    result.append('\n');
                    break;
                case 'r':
                    result.append('\r');
                    break;
                case 't':
                    result.append('\t');
                    break;
                case 'u':
                    result.append(readUnicodeEscape());
                    break;
                default:
                    fail("invalid JSON escape");
                }
            } else {
                if (current < 0x20) {
                    fail("unescaped control character in string");
                }
                result.append(current);
            }
        }
        fail("unterminated JSON string");
        return null;
    }

    private char readUnicodeEscape() throws CommandValidationException {
        if (text.length() - offset < 4) {
            fail("truncated Unicode escape");
        }
        int value = 0;
        for (int index = 0; index < 4; index++) {
            int digit = Character.digit(text.charAt(offset++), 16);
            if (digit < 0) {
                fail("invalid Unicode escape");
            }
            value = (value << 4) | digit;
        }
        return (char) value;
    }

    private Number readNumber() throws CommandValidationException {
        int start = offset;
        consume('-');
        if (consume('0')) {
            if (offset < text.length() && isDigit(text.charAt(offset))) {
                fail("leading zero in JSON number");
            }
        } else {
            requireDigits();
        }
        boolean decimal = false;
        if (consume('.')) {
            decimal = true;
            requireDigits();
        }
        if (offset < text.length()
                && (text.charAt(offset) == 'e' || text.charAt(offset) == 'E')) {
            decimal = true;
            offset++;
            if (offset < text.length()
                    && (text.charAt(offset) == '+' || text.charAt(offset) == '-')) {
                offset++;
            }
            requireDigits();
        }
        String token = text.substring(start, offset);
        try {
            if (!decimal) {
                return Long.valueOf(token);
            }
            double value = Double.parseDouble(token);
            if (!Double.isFinite(value)) {
                fail("non-finite JSON number");
            }
            return Double.valueOf(value);
        } catch (NumberFormatException failure) {
            throw new CommandValidationException("JSON number is out of range", failure);
        }
    }

    private void requireDigits() throws CommandValidationException {
        int start = offset;
        while (offset < text.length() && isDigit(text.charAt(offset))) {
            offset++;
        }
        if (start == offset) {
            fail("JSON number requires digits");
        }
    }

    private void readLiteral(String literal) throws CommandValidationException {
        if (!text.regionMatches(offset, literal, 0, literal.length())) {
            fail("invalid JSON literal");
        }
        offset += literal.length();
    }

    private boolean consume(char expected) {
        if (offset < text.length() && text.charAt(offset) == expected) {
            offset++;
            return true;
        }
        return false;
    }

    private void require(char expected) throws CommandValidationException {
        if (!consume(expected)) {
            fail("expected '" + expected + "'");
        }
    }

    private void skipWhitespace() {
        while (offset < text.length()) {
            char current = text.charAt(offset);
            if (current != ' ' && current != '\t' && current != '\r' && current != '\n') {
                return;
            }
            offset++;
        }
    }

    private void validateSurrogates(StringBuilder value) throws CommandValidationException {
        for (int index = 0; index < value.length(); index++) {
            char current = value.charAt(index);
            if (Character.isHighSurrogate(current)) {
                if (index + 1 >= value.length()
                        || !Character.isLowSurrogate(value.charAt(index + 1))) {
                    fail("unpaired high surrogate in JSON string");
                }
                index++;
            } else if (Character.isLowSurrogate(current)) {
                fail("unpaired low surrogate in JSON string");
            }
        }
    }

    private void fail(String message) throws CommandValidationException {
        throw new CommandValidationException(message + " at character " + offset);
    }

    private static boolean isDigit(char value) {
        return value >= '0' && value <= '9';
    }
}
