package xiaozhi.modules.zs.service;

import java.util.List;

import xiaozhi.modules.zs.dto.FamilyMemberBatchSaveDTO;
import xiaozhi.modules.zs.dto.FamilyMemberRespDTO;
import xiaozhi.modules.zs.dto.FamilyMemberSaveDTO;
import xiaozhi.modules.zs.dto.FamilyMemberUpdateDTO;

public interface FamilyMemberService {

    /**
     * 保存亲属
     *
     * @param userId 用户ID
     * @param dto    保存请求
     * @return 亲属响应
     */
    FamilyMemberRespDTO save(Long userId, FamilyMemberSaveDTO dto);

    /**
     * 批量保存亲属
     *
     * @param userId 用户ID
     * @param dto    批量保存请求
     * @return 亲属响应列表
     */
    List<FamilyMemberRespDTO> saveBatch(Long userId, FamilyMemberBatchSaveDTO dto);

    /**
     * 查询亲属列表
     *
     * @param userId      用户ID
     * @param verifyCode  设备验证码
     * @return 亲属列表
     */
    List<FamilyMemberRespDTO> list(Long userId, String verifyCode);

    /**
     * 根据设备ID查询有效亲属列表
     *
     * @param deviceId 设备ID
     * @return 亲属列表
     */
    List<FamilyMemberRespDTO> listByDeviceId(String deviceId);

    /**
     * 更新亲属
     *
     * @param userId 用户ID
     * @param dto    更新请求
     * @return 亲属响应
     */
    FamilyMemberRespDTO update(Long userId, FamilyMemberUpdateDTO dto);

    /**
     * 删除亲属
     *
     * @param userId     用户ID
     * @param verifyCode 设备验证码
     * @param memberId   亲属ID
     */
    void delete(Long userId, String verifyCode, Integer memberId);
}
