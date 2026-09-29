import apiClient from "../../utils/request";
import { API_ENDPOINTS } from "../../config";

export const fetchCurrentUser = () => apiClient.get(API_ENDPOINTS.USER_INFO);

export const registerAccount = (username, email, password) =>
  apiClient.post(API_ENDPOINTS.REGISTER, { username, email, password });

export const loginWithPassword = (username, password) => {
  const formData = new FormData();
  formData.append("username", username);
  formData.append("password", password);

  // Let the browser set Content-Type (with boundary) for this FormData request.
  return apiClient.post(API_ENDPOINTS.LOGIN, formData);
};

export const logoutCurrentSession = () => apiClient.post(API_ENDPOINTS.LOGOUT);
