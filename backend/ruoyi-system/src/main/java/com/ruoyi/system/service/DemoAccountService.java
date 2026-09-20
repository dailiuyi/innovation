package com.ruoyi.system.service;

import com.ruoyi.common.core.domain.entity.SysUser;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.common.utils.SecurityUtils;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Fixed-role account policy. The shared role row serializes account mutations. */
@Service
public class DemoAccountService {
    private final JdbcTemplate jdbc;
    private final ISysUserService users;
    public DemoAccountService(JdbcTemplate jdbc, ISysUserService users) { this.jdbc = jdbc; this.users = users; }
    public static void validatePassword(String password) {
        if (password == null || password.length() < 6 || password.length() > 64)
            throw new ServiceException("密码长度必须为 6–64 个字符");
    }
    private void lock() { jdbc.queryForObject("select role_id from sys_role where role_id=100 for update", Long.class); }
    @Transactional
    public int create(SysUser input) {
        lock();
        validatePassword(input.getPassword());
        if (input.getUserName() == null || !input.getUserName().matches("[A-Za-z0-9_]{3,30}"))
            throw new ServiceException("账号须为 3–30 位字母、数字或下划线");
        if (input.getNickName() == null || input.getNickName().isBlank() || input.getNickName().length()>30)
            throw new ServiceException("请填写 1–30 字的姓名");
        if (jdbc.queryForObject("select count(*) from sys_user where user_name=?", Long.class, input.getUserName()) > 0)
            throw new ServiceException("账号已存在或已删除，请使用其他账号名");
        SysUser user = new SysUser();
        user.setUserName(input.getUserName()); user.setNickName(input.getNickName());
        user.setPassword(SecurityUtils.encryptPassword(input.getPassword()));
        user.setDeptId(100L); user.setRoleIds(new Long[]{100L}); user.setStatus("0");
        user.setCreateBy(SecurityUtils.getUsername());
        int count = users.insertUser(user);
        jdbc.update("update sys_user set pwd_update_date=now() where user_id=?",user.getUserId());
        jdbc.update("update sys_user set status='1',update_time=now() where user_name='bootstrap'");
        return count;
    }
    @Transactional
    public int status(Long id, String status) {
        lock();
        if (!"0".equals(status) && !"1".equals(status)) throw new ServiceException("账号状态无效");
        SysUser target = users.selectUserById(id);
        if (target == null || !"0".equals(target.getDelFlag())) throw new ServiceException("账号不存在");
        if ("bootstrap".equals(target.getUserName())) throw new ServiceException("引导账号不能重新启用");
        if ("1".equals(status) && "0".equals(target.getStatus()) && jdbc.queryForObject(
            "select count(*) from sys_user where status='0' and del_flag='0'", Long.class) <= 1)
            throw new ServiceException("不能禁用最后一个有效管理员");
        return jdbc.update("update sys_user set status=?,update_by=?,update_time=now() where user_id=?", status, SecurityUtils.getUsername(), id);
    }
    @Transactional
    public int delete(Long id) {
        lock();
        SysUser target = users.selectUserById(id);
        if (target == null || !"0".equals(target.getDelFlag())) throw new ServiceException("账号不存在或已删除");
        if ("0".equals(target.getStatus()) && jdbc.queryForObject(
            "select count(*) from sys_user where status='0' and del_flag='0'", Long.class) <= 1)
            throw new ServiceException("不能删除最后一个有效管理员");
        if (SecurityUtils.getUserId().equals(id)) throw new ServiceException("不能删除当前登录账号，请使用其他管理员账号操作");
        return jdbc.update("update sys_user set del_flag='2',status='1',credential_epoch=credential_epoch+1,update_by=?,update_time=now() where user_id=? and del_flag='0'",
            SecurityUtils.getUsername(), id);
    }
    @Transactional
    public int password(Long id, String password) {
        lock(); validatePassword(password);
        SysUser target = users.selectUserById(id);
        if (target==null || !"0".equals(target.getDelFlag())) throw new ServiceException("账号不存在");
        return jdbc.update("update sys_user set password=?,pwd_update_date=now(),update_by=?,update_time=now() where user_id=?",
            SecurityUtils.encryptPassword(password),SecurityUtils.getUsername(),id);
    }
}
