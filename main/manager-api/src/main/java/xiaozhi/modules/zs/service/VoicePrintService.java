package xiaozhi.modules.zs.service;

import java.util.List;

import xiaozhi.modules.zs.dto.VoicePrintRespDTO;
import xiaozhi.modules.zs.dto.VoicePrintSaveDTO;
import xiaozhi.modules.zs.dto.VoicePrintUpdateDTO;

/**
 * 声纹录音服务接口
 */
public interface VoicePrintService {

    /**
     * 保存声纹录音
     *
     * @param userId 用户ID
     * @param dto    保存请求参数
     * @return 声纹响应
     */
    VoicePrintRespDTO save(Long userId, VoicePrintSaveDTO dto);

    /**
     * 获取声纹列表
     *
     * @param userId     用户ID
     * @param verifyCode 设备验证码
     * @return 声纹列表
     */
    List<VoicePrintRespDTO> list(Long userId, String verifyCode);

    /**
     * 更新声纹
     *
     * @param userId 用户ID
     * @param dto    更新请求参数
     * @return 声纹响应
     */
    VoicePrintRespDTO update(Long userId, VoicePrintUpdateDTO dto);

    /**
     * 删除声纹
     *
     * @param userId     用户ID
     * @param verifyCode 设备验证码
     * @param voiceId    声纹ID
     */
    void delete(Long userId, String verifyCode, String voiceId);
}
