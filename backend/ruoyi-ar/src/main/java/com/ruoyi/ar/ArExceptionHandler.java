package com.ruoyi.ar;

import java.util.Map;
import java.util.UUID;
import org.slf4j.LoggerFactory;
import org.springframework.core.annotation.Order;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestControllerAdvice(basePackages="com.ruoyi.ar") @Order(-100)
public class ArExceptionHandler {
    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String,String>> handle(Exception e) {
        int status=500;String message="服务内部错误";
        if(e instanceof ResponseStatusException r) {status=r.getStatusCode().value();message=r.getReason();}
        else if(e instanceof org.springframework.web.bind.MethodArgumentNotValidException
             || e instanceof org.springframework.web.bind.MissingServletRequestParameterException
             || e instanceof jakarta.validation.ConstraintViolationException
             || e instanceof org.springframework.http.converter.HttpMessageNotReadableException
             || e instanceof org.springframework.web.method.annotation.MethodArgumentTypeMismatchException) {status=400;message="请求字段不合法";}
        String trace=UUID.randomUUID().toString();
        if(status==500) LoggerFactory.getLogger(getClass()).error("AR failure traceId={}",trace,e);
        return ResponseEntity.status(status).body(Map.of("code","AR_"+status,"message",message==null?"请求失败":message,"traceId",trace));
    }
}
