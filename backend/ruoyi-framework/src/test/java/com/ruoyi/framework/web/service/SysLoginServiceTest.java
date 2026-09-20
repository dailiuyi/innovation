package com.ruoyi.framework.web.service;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import java.util.Set;
import java.util.concurrent.ScheduledExecutorService;
import com.ruoyi.common.core.domain.entity.SysUser;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.common.core.redis.RedisCache;
import com.ruoyi.common.exception.user.UserPasswordNotMatchException;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.common.utils.spring.SpringUtils;
import com.ruoyi.framework.security.context.AuthenticationContextHolder;
import com.ruoyi.system.service.DemoAccountService;
import com.ruoyi.system.service.ISysConfigService;
import com.ruoyi.system.service.ISysUserService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.context.support.StaticMessageSource;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

class SysLoginServiceTest {
    private SysLoginService login;
    private ISysUserService users;
    private TokenService tokens;

    @BeforeAll
    static void configureAsyncLogging() {
        // Do not execute audit tasks or connect to external services in this unit test.
        DefaultListableBeanFactory beans = new DefaultListableBeanFactory();
        beans.registerSingleton("scheduledExecutorService", mock(ScheduledExecutorService.class));
        StaticMessageSource messages = new StaticMessageSource();
        messages.setUseCodeAsDefaultMessage(true);
        beans.registerSingleton("messageSource", messages);
        new SpringUtils().postProcessBeanFactory(beans);
    }

    @BeforeEach
    void setUp() {
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(new MockHttpServletRequest()));
        users = mock(ISysUserService.class);
        tokens = mock(TokenService.class);
        ISysConfigService config = mock(ISysConfigService.class);
        when(config.selectConfigByKey("sys.login.blackIPList")).thenReturn("");
        SysPasswordService passwords = new SysPasswordService();
        ReflectionTestUtils.setField(passwords, "redisCache", mock(RedisCache.class));
        ReflectionTestUtils.setField(passwords, "maxRetryCount", 5);
        ReflectionTestUtils.setField(passwords, "lockTime", 10);
        SysPermissionService permissions = mock(SysPermissionService.class);
        when(permissions.getMenuPermission(any())).thenReturn(Set.of("*:*:*"));
        UserDetailsServiceImpl details = new UserDetailsServiceImpl();
        ReflectionTestUtils.setField(details, "userService", users);
        ReflectionTestUtils.setField(details, "passwordService", passwords);
        ReflectionTestUtils.setField(details, "permissionService", permissions);
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(details);
        provider.setPasswordEncoder(new BCryptPasswordEncoder());
        login = new SysLoginService();
        ReflectionTestUtils.setField(login, "authenticationManager", new ProviderManager(provider));
        ReflectionTestUtils.setField(login, "configService", config);
        ReflectionTestUtils.setField(login, "userService", users);
        ReflectionTestUtils.setField(login, "tokenService", tokens);
    }

    @AfterEach
    void clearRequest() {
        RequestContextHolder.resetRequestAttributes();
        AuthenticationContextHolder.clearContext();
    }

    @ParameterizedTest
    @ValueSource(ints = {6, 11, 64})
    void acceptedAccountPasswordCanLogIn(int length) {
        String password = "a".repeat(length);
        DemoAccountService.validatePassword(password);
        SysUser user = new SysUser();
        user.setUserId(100L);
        user.setUserName("boundary_admin");
        user.setStatus("0");
        user.setDelFlag("0");
        user.setPassword(SecurityUtils.encryptPassword(password));
        when(users.selectUserByUserName("boundary_admin")).thenReturn(user);
        when(tokens.createToken(any(LoginUser.class))).thenReturn("synthetic-session");

        // Exercise loginPreCheck, UserDetailsService and BCrypt, not a mocked login.
        assertEquals("synthetic-session", login.login("boundary_admin", password, null, null));
        verify(tokens).createToken(argThat(u -> u.getUserId().equals(100L)));
        assertNull(AuthenticationContextHolder.getContext());
    }

    @ParameterizedTest
    @ValueSource(ints = {5, 65})
    void invalidLengthIsRejectedBeforeAuthentication(int length) {
        assertThrows(UserPasswordNotMatchException.class,
            () -> login.login("boundary_admin", "a".repeat(length), null, null));
        verifyNoInteractions(users, tokens);
    }
}
