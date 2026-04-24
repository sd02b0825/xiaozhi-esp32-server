package xiaozhi.modules.zs.service.impl;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.exception.RenException;
import xiaozhi.modules.device.dao.DeviceDao;
import xiaozhi.modules.device.entity.DeviceEntity;
import xiaozhi.modules.zs.dao.FamilyMemberDao;
import xiaozhi.modules.zs.dto.FamilyMemberBatchSaveDTO;
import xiaozhi.modules.zs.dto.FamilyMemberRespDTO;
import xiaozhi.modules.zs.dto.FamilyMemberSaveDTO;
import xiaozhi.modules.zs.dto.FamilyMemberUpdateDTO;
import xiaozhi.modules.zs.entity.FamilyMemberEntity;
import xiaozhi.modules.zs.service.FamilyMemberService;

@Slf4j
@Service
@RequiredArgsConstructor
public class FamilyMemberServiceImpl implements FamilyMemberService {

    private final FamilyMemberDao familyMemberDao;
    private final DeviceDao deviceDao;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public FamilyMemberRespDTO save(Long userId, FamilyMemberSaveDTO dto) {
        // 1. 根据验证码查询设备
        DeviceEntity device = getDeviceByVerifyCode(dto.getVerifyCode(), userId);
        if (device == null) {
            throw new RenException("设备不存在");
        }

        // 2. 构建实体
        FamilyMemberEntity entity = new FamilyMemberEntity();
        entity.setUserId(userId);
        entity.setDeviceId(device.getId());
        entity.setAgentId(device.getAgentId());
        entity.setName(dto.getName());
        entity.setPhone(dto.getPhone());
        entity.setRemark(dto.getRemark());
        entity.setStatus(1);
        entity.setSort(0);
        entity.setCreator(userId);
        entity.setUpdater(userId);
        entity.setCreateDate(new Date());
        entity.setUpdateDate(new Date());

        // 3. 保存
        familyMemberDao.insert(entity);
        log.info("亲属保存成功: id={}, name={}", entity.getId(), entity.getName());

        return toRespDTO(entity);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public List<FamilyMemberRespDTO> saveBatch(Long userId, FamilyMemberBatchSaveDTO dto) {
        // 1. 根据验证码查询设备
        DeviceEntity device = getDeviceByVerifyCode(dto.getVerifyCode(), userId);
        if (device == null) {
            throw new RenException("设备不存在");
        }

        // 2. 批量构建并保存
        Date now = new Date();
        List<FamilyMemberEntity> entities = dto.getMembers().stream().map(member -> {
            FamilyMemberEntity entity = new FamilyMemberEntity();
            entity.setUserId(userId);
            entity.setDeviceId(device.getId());
            entity.setAgentId(device.getAgentId());
            entity.setName(member.getName());
            entity.setPhone(member.getPhone());
            entity.setRemark(member.getRemark());
            entity.setStatus(1);
            entity.setSort(0);
            entity.setCreator(userId);
            entity.setUpdater(userId);
            entity.setCreateDate(now);
            entity.setUpdateDate(now);
            return entity;
        }).toList();

        entities.forEach(familyMemberDao::insert);
        log.info("亲属批量保存成功: count={}", entities.size());

        return entities.stream().map(this::toRespDTO).collect(Collectors.toList());
    }

    @Override
    public List<FamilyMemberRespDTO> list(Long userId, String verifyCode) {
        // 1. 根据验证码查询设备
        DeviceEntity device = getDeviceByVerifyCode(verifyCode, userId);
        if (device == null) {
            throw new RenException("设备不存在");
        }

        // 2. 查询亲属列表
        List<FamilyMemberEntity> list = familyMemberDao.selectList(
                new LambdaQueryWrapper<FamilyMemberEntity>()
                        .eq(FamilyMemberEntity::getUserId, userId)
                        .eq(FamilyMemberEntity::getDeviceId, device.getId())
                        .eq(FamilyMemberEntity::getStatus, 1)
                        .orderByAsc(FamilyMemberEntity::getSort)
                        .orderByDesc(FamilyMemberEntity::getCreateDate));

        return list.stream().map(this::toRespDTO).collect(Collectors.toList());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public FamilyMemberRespDTO update(Long userId, FamilyMemberUpdateDTO dto) {
        // 1. 根据验证码查询设备
        DeviceEntity device = getDeviceByVerifyCode(dto.getVerifyCode(), userId);
        if (device == null) {
            throw new RenException("设备不存在");
        }

        // 2. 查询亲属
        FamilyMemberEntity entity = familyMemberDao.selectOne(
                new LambdaQueryWrapper<FamilyMemberEntity>()
                        .eq(FamilyMemberEntity::getId, dto.getId())
                        .eq(FamilyMemberEntity::getUserId, userId)
                        .eq(FamilyMemberEntity::getDeviceId, device.getId()));
        if (entity == null) {
            throw new RenException("亲属不存在或无权操作");
        }

        // 3. 更新字段
        entity.setName(dto.getName());
        entity.setPhone(dto.getPhone());
        entity.setRemark(dto.getRemark());
        entity.setUpdater(userId);
        entity.setUpdateDate(new Date());

        familyMemberDao.updateById(entity);
        log.info("亲属更新成功: id={}, name={}", entity.getId(), entity.getName());

        return toRespDTO(entity);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void delete(Long userId, String verifyCode, Long memberId) {
        // 1. 根据验证码查询设备
        DeviceEntity device = getDeviceByVerifyCode(verifyCode, userId);
        if (device == null) {
            throw new RenException("设备不存在");
        }

        // 2. 查询并删除
        FamilyMemberEntity entity = familyMemberDao.selectOne(
                new LambdaQueryWrapper<FamilyMemberEntity>()
                        .eq(FamilyMemberEntity::getId, memberId)
                        .eq(FamilyMemberEntity::getUserId, userId)
                        .eq(FamilyMemberEntity::getDeviceId, device.getId()));
        if (entity == null) {
            throw new RenException("亲属不存在或无权操作");
        }

        familyMemberDao.deleteById(memberId);
        log.info("亲属删除成功: id={}", memberId);
    }

    private DeviceEntity getDeviceByVerifyCode(String verifyCode, Long userId) {
        return deviceDao.selectOne(
                new LambdaQueryWrapper<DeviceEntity>()
                        .eq(DeviceEntity::getVerifyCode, verifyCode)
                        .eq(DeviceEntity::getUserId, userId));
    }

    private FamilyMemberRespDTO toRespDTO(FamilyMemberEntity entity) {
        FamilyMemberRespDTO dto = new FamilyMemberRespDTO();
        dto.setId(entity.getId());
        dto.setDeviceId(entity.getDeviceId());
        dto.setAgentId(entity.getAgentId());
        dto.setName(entity.getName());
        dto.setPhone(entity.getPhone());
        dto.setRemark(entity.getRemark());
        dto.setStatus(entity.getStatus());
        dto.setCreateDate(entity.getCreateDate() != null
                ? new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(entity.getCreateDate())
                : null);
        return dto;
    }
}
