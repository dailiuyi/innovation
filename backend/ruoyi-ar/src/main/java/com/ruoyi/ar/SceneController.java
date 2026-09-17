package com.ruoyi.ar;

import java.util.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

@RestController @RequestMapping("/api/v1") @Validated
public class SceneController {
    private final SceneService service; private final SceneMapper mapper;
    public SceneController(SceneService service,SceneMapper mapper) {this.service=service;this.mapper=mapper;}
    @GetMapping("/scenes") public Map<String,Object> list(@RequestParam(defaultValue="") @Size(max=200) String name,
        @RequestParam(defaultValue="20") @Min(1) @Max(100) int limit,@RequestParam(defaultValue="0") @Min(0) int offset) {
        return Map.of("items",mapper.list(name,limit,offset),"total",mapper.count(name));
    }
    @GetMapping("/scenes/{id}") public Map<String,Object> detail(@PathVariable UUID id) {return service.find(id.toString());}
    @DeleteMapping("/scenes/{id}") @ResponseStatus(org.springframework.http.HttpStatus.NO_CONTENT)
    public void delete(@PathVariable UUID id,@RequestParam @Min(0) long expectedVersion) {service.delete(id.toString(),expectedVersion);}
    @PostMapping("/scenes") @ResponseStatus(org.springframework.http.HttpStatus.CREATED)
    public Map<String,Object> create(@Valid @RequestBody SceneInput s) {return service.create(s);}
    @PutMapping("/scenes/{id}") public Map<String,Object> update(@PathVariable UUID id,@Valid @RequestBody SceneInput s) {return service.update(id.toString(),s);}
    public record EnabledInput(@NotNull Boolean enabled,@NotNull @Min(0) Long expectedVersion,@NotBlank @Size(max=1000) String reason) {}
    @PutMapping("/scenes/{id}/enabled") public Map<String,Object> enabled(@PathVariable UUID id,@Valid @RequestBody EnabledInput s) {return service.enabled(id.toString(),s.enabled(),s.expectedVersion(),s.reason());}
    @GetMapping("/audits") public Map<String,Object> audits(@RequestParam(defaultValue="20") @Min(1) @Max(100) int limit,@RequestParam(defaultValue="0") @Min(0) int offset) {
        return Map.of("items",mapper.audits(limit,offset),"total",mapper.auditCount());
    }
}
