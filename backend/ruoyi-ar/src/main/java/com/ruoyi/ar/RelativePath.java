package com.ruoyi.ar;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

/** Export paths only. Server storage still uses UUID.bin and never writes these names. */
public final class RelativePath {
    public static final int MAX_PATH = 1024;
    public static final int MAX_SEGMENT = 255;
    public static final int MAX_DEPTH = 32;
    private static final Pattern RESERVED = Pattern.compile("^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\\..*)?$", Pattern.CASE_INSENSITIVE);

    private RelativePath() {}

    public static String normalizeOne(String raw) {
        if (raw == null || raw.isEmpty()) throw new IllegalArgumentException("相对路径不能为空");
        if (raw.indexOf('\0') >= 0) throw new IllegalArgumentException("相对路径不能包含空字符");
        if (raw.length() > MAX_PATH) throw new IllegalArgumentException("相对路径过长");
        if (raw.startsWith("/") || raw.startsWith("\\") || raw.startsWith("//")
                || (raw.length() >= 2 && Character.isLetter(raw.charAt(0)) && raw.charAt(1) == ':')) {
            throw new IllegalArgumentException("相对路径不能为绝对路径");
        }
        if (raw.indexOf('\\') >= 0) throw new IllegalArgumentException("相对路径不能包含反斜杠");
        String path = Normalizer.normalize(raw, Normalizer.Form.NFC);
        if (path.startsWith("/") || path.endsWith("/") || path.contains("//")) {
            throw new IllegalArgumentException("相对路径格式不合法");
        }
        String[] parts = path.split("/", -1);
        if (parts.length == 0 || parts.length > MAX_DEPTH) throw new IllegalArgumentException("相对路径层级不合法");
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < parts.length; i++) {
            validateSegment(parts[i]);
            if (i > 0) out.append('/');
            out.append(parts[i]);
        }
        String result = out.toString();
        if (result.length() > MAX_PATH) throw new IllegalArgumentException("相对路径过长");
        return result;
    }

    public static List<String> normalizeAll(List<String> paths) {
        List<String> result = new ArrayList<>(paths.size());
        Set<String> seen = new HashSet<>();
        Set<String> seenLower = new HashSet<>();
        for (String raw : paths) result.add(normalizeOne(raw));
        List<String> sorted = new ArrayList<>(result);
        sorted.sort(String::compareTo);
        for (String path : sorted) {
            if (!seen.add(path)) throw new IllegalArgumentException("相对路径重复");
            if (!seenLower.add(path.toLowerCase(Locale.ROOT))) throw new IllegalArgumentException("相对路径存在规范化或大小写冲突");
        }
        List<String> folded = new ArrayList<>();
        for (String path : result) folded.add(path.toLowerCase(Locale.ROOT));
        folded.sort(String::compareTo);
        for (int i = 0; i < folded.size(); i++) {
            String prefix = folded.get(i);
            for (int j = i + 1; j < folded.size(); j++) {
                String next = folded.get(j);
                if (!next.startsWith(prefix)) break;
                if (next.startsWith(prefix + "/")) throw new IllegalArgumentException("文件与目录路径冲突");
            }
        }
        return result;
    }

    /** Deterministic export path. Keeps a valid relative path, including nested directories. */
    public static String safeExportPath(String fileName, java.util.UUID fileId) {
        if (fileName == null || fileId == null) throw new IllegalArgumentException("相对路径不能为空");
        try { return normalizeOne(fileName); }
        catch (IllegalArgumentException ignored) { }
        String segment = fileName.replace('\\', '_');
        StringBuilder cleaned = new StringBuilder();
        for (int i = 0; i < segment.length(); i++) {
            char c = segment.charAt(i);
            cleaned.append(c < 32 || c == 127 || "<>:\"|?*".indexOf(c) >= 0 ? '_' : c);
        }
        segment = cleaned.toString().replaceAll("^[ ]+", "").replaceAll("[. ]+$", "");
        if (segment.isEmpty() || ".".equals(segment) || "..".equals(segment) || RESERVED.matcher(segment).matches()) {
            int dot = fileName.lastIndexOf('.');
            String ext = "";
            if (dot > 0 && fileName.substring(dot).matches("\\.[A-Za-z0-9]{1,20}")) ext = fileName.substring(dot);
            segment = "export-" + fileId.toString().substring(0, 8) + ext;
        }
        if (segment.length() > MAX_SEGMENT) segment = segment.substring(0, MAX_SEGMENT);
        return segment;
    }

    public static String fileName(String relativePath) {
        int index = relativePath.lastIndexOf('/');
        return index < 0 ? relativePath : relativePath.substring(index + 1);
    }

    private static void validateSegment(String segment) {
        if (segment.isEmpty()) throw new IllegalArgumentException("相对路径含有空片段");
        if (segment.length() > MAX_SEGMENT) throw new IllegalArgumentException("路径片段过长");
        if (".".equals(segment) || "..".equals(segment)) throw new IllegalArgumentException("相对路径不能包含越界片段");
        if (segment.charAt(0) == ' ' || segment.endsWith(" ") || segment.endsWith(".")) {
            throw new IllegalArgumentException("路径片段不能以空格开头，也不能以空格或点号结尾");
        }
        for (int i = 0; i < segment.length(); i++) {
            char c = segment.charAt(i);
            if (c < 32 || c == 127 || "<>:\"|?*".indexOf(c) >= 0) {
                throw new IllegalArgumentException("路径包含不能安全还原的字符");
            }
        }
        if (RESERVED.matcher(segment).matches()) throw new IllegalArgumentException("路径包含目标环境保留名称");
    }
}
