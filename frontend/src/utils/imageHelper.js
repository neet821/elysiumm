import { API_BASE_URL } from '../config';

/**
 * 处理图片URL，确保能正确显示
 * @param {string} url - 原始URL（可能是相对路径或完整URL）
 * @returns {string} - 完整的可访问URL
 */
export const getImageUrl = (url) => {
  if (!url) return '';

  // 如果已经是完整的HTTP/HTTPS URL，直接返回
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url;
  }

  // 如果是相对路径（如 /uploads/xxx），拼接API基础URL
  if (url.startsWith('/')) {
    return `${API_BASE_URL}${url}`;
  }

  // 如果既不是完整URL也不以/开头，假设是相对路径，添加/前缀
  return `${API_BASE_URL}/${url}`;
};

/**
 * 检查图片URL是否有效
 * @param {string} url - 图片URL
 * @returns {Promise<boolean>} - 是否有效
 */
export const checkImageValid = async (url) => {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(true);
    img.onerror = () => resolve(false);
    img.src = url;

    // 5秒超时
    setTimeout(() => resolve(false), 5000);
  });
};

/**
 * 获取带有fallback的图片URL
 * @param {string} url - 原始URL
 * @param {string} fallback - 备用URL
 * @returns {string} - 处理后的URL
 */
export const getImageUrlWithFallback = (url, fallback = '/placeholder.png') => {
  const processedUrl = getImageUrl(url);
  return processedUrl || fallback;
};
