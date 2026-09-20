package com.ruoyi.system.service;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.ruoyi.common.exception.ServiceException;
import org.junit.jupiter.api.Test;

class DemoAccountServiceTest {
    @Test
    void validatesPasswordLengthBoundaries() {
        ServiceException tooShort = assertThrows(ServiceException.class,
            () -> DemoAccountService.validatePassword("a".repeat(5)));
        assertEquals("密码长度必须为 6–64 个字符", tooShort.getMessage());

        assertDoesNotThrow(() -> DemoAccountService.validatePassword("a".repeat(6)));
        assertDoesNotThrow(() -> DemoAccountService.validatePassword("a".repeat(64)));

        ServiceException tooLong = assertThrows(ServiceException.class,
            () -> DemoAccountService.validatePassword("a".repeat(65)));
        assertEquals("密码长度必须为 6–64 个字符", tooLong.getMessage());
    }
}
