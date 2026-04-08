import encoding from "k6/encoding";
import exec from "k6/execution";
import http from "k6/http";
import { Rate, Trend } from "k6/metrics";
import { check, sleep } from "k6";

const BASE_URL = __ENV.API_BASE_URL || "http://127.0.0.1:8000";
const WORKLOAD_USER = __ENV.K6_USER_ID || "perf-user";
const WORKLOAD_PROJECT = __ENV.K6_PROJECT_ID || "perf-project";

const QUERY_DURATION = new Trend("chat_query_duration", true);
const QUERY_FAILED = new Rate("chat_query_failed");

export const options = {
  scenarios: {
    query_50: {
      executor: "constant-vus",
      vus: Number(__ENV.K6_VUS_50 || 50),
      duration: __ENV.K6_DURATION_50 || "15s",
      gracefulStop: "5s"
    },
    query_100: {
      executor: "constant-vus",
      vus: Number(__ENV.K6_VUS_100 || 100),
      duration: __ENV.K6_DURATION_100 || "15s",
      startTime: __ENV.K6_START_100 || "20s",
      gracefulStop: "5s"
    }
  },
  thresholds: {
    "chat_query_duration{scenario:query_50}": ["p(95)<2500"],
    "http_req_failed{scenario:query_100}": ["rate<0.01"],
    http_req_failed: ["rate<0.01"],
    chat_query_failed: ["rate<0.01"]
  }
};

const PERF_XLSX_BASE64 =
  "UEsDBBQAAAAIAG5biFxGx01IlQAAAM0AAAAQAAAAZG9jUHJvcHMvYXBwLnhtbE3PTQvCMAwG4L9SdreZih6kDkQ9ip68zy51hbYpbYT67+0EP255ecgboi6JIia2mEXxLuRtMzLHDUDWI/o+y8qhiqHke64x3YGMsRoPpB8eA8OibdeAhTEMOMzit7Dp1C5GZ3XPlkJ3sjpRJsPiWDQ6sScfq9wcChDneiU+ixNLOZcrBf+LU8sVU57mym/8ZAW/B7oXUEsDBBQAAAAIAG5biFxZSoy46wAAAMsBAAARAAAAZG9jUHJvcHMvY29yZS54bWylkU1PwzAMhv/KlHvrtEVjirpeQJxAQmISaLco8bZqzYcSo3b/nrRs3RDcOMbv48e2UisvlAv4GpzHQC3GxWA6G4Xya3Yg8gIgqgMaGfNE2BTuXDCS0jPswUt1lHuEkvMlGCSpJUkYhZmfjeys1GpW+s/QTQKtADs0aClCkRdwZQmDiX82TMlMDrGdqb7v876auLRRAR8vz2/T8llrI0mrkDW1VkIFlORCM17kT0NXw02xPs/+LqBepAmCTh7X7JK8Vw+PmyfWlLxcZvwu46sNr0R5L8rVdnT96L8KjdPtrv2H8SJoavj1b80XUEsDBBQAAAAIAG5biFyZXJwjEAYAAJwnAAATAAAAeGwvdGhlbWUvdGhlbWUxLnhtbO1aW3PaOBR+76/QeGf2bQvGNoG2tBNzaXbbtJmE7U4fhRFYjWx5ZJGEf79HNhDLlg3tkk26mzwELOn7zkVH5+g4efPuLmLohoiU8nhg2S/b1ru3L97gVzIkEUEwGaev8MAKpUxetVppAMM4fckTEsPcgosIS3gUy9Zc4FsaLyPW6rTb3VaEaWyhGEdkYH1eLGhA0FRRWm9fILTlHzP4FctUjWWjARNXQSa5iLTy+WzF/NrePmXP6TodMoFuMBtYIH/Ob6fkTlqI4VTCxMBqZz9Wa8fR0kiAgsl9lAW6Sfaj0xUIMg07Op1YznZ89sTtn4zK2nQ0bRrg4/F4OLbL0otwHATgUbuewp30bL+kQQm0o2nQZNj22q6RpqqNU0/T933f65tonAqNW0/Ta3fd046Jxq3QeA2+8U+Hw66JxqvQdOtpJif9rmuk6RZoQkbj63oSFbXlQNMgAFhwdtbM0gOWXin6dZQa2R273UFc8FjuOYkR/sbFBNZp0hmWNEZynZAFDgA3xNFMUHyvQbaK4MKS0lyQ1s8ptVAaCJrIgfVHgiHF3K/99Ze7yaQzep19Os5rlH9pqwGn7bubz5P8c+jkn6eT101CznC8LAnx+yNbYYcnbjsTcjocZ0J8z/b2kaUlMs/v+QrrTjxnH1aWsF3Pz+SejHIju932WH32T0duI9epwLMi15RGJEWfyC265BE4tUkNMhM/CJ2GmGpQHAKkCTGWoYb4tMasEeATfbe+CMjfjYj3q2+aPVehWEnahPgQRhrinHPmc9Fs+welRtH2Vbzco5dYFQGXGN80qjUsxdZ4lcDxrZw8HRMSzZQLBkGGlyQmEqk5fk1IE/4rpdr+nNNA8JQvJPpKkY9psyOndCbN6DMawUavG3WHaNI8ev4F+Zw1ChyRGx0CZxuzRiGEabvwHq8kjpqtwhErQj5iGTYacrUWgbZxqYRgWhLG0XhO0rQR/FmsNZM+YMjszZF1ztaRDhGSXjdCPmLOi5ARvx6GOEqa7aJxWAT9nl7DScHogstm/bh+htUzbCyO90fUF0rkDyanP+kyNAejmlkJvYRWap+qhzQ+qB4yCgXxuR4+5Xp4CjeWxrxQroJ7Af/R2jfCq/iCwDl/Ln3Ppe+59D2h0rc3I31nwdOLW95GblvE+64x2tc0LihjV3LNyMdUr5Mp2DmfwOz9aD6e8e362SSEr5pZLSMWkEuBs0EkuPyLyvAqxAnoZFslCctU02U3ihKeQhtu6VP1SpXX5a+5KLg8W+Tpr6F0PizP+Txf57TNCzNDt3JL6raUvrUmOEr0scxwTh7LDDtnPJIdtnegHTX79l125COlMFOXQ7gaQr4Dbbqd3Do4npiRuQrTUpBvw/npxXga4jnZBLl9mFdt59jR0fvnwVGwo+88lh3HiPKiIe6hhpjPw0OHeXtfmGeVxlA0FG1srCQsRrdguNfxLBTgZGAtoAeDr1EC8lJVYDFbxgMrkKJ8TIxF6HDnl1xf49GS49umZbVuryl3GW0iUjnCaZgTZ6vK3mWxwVUdz1Vb8rC+aj20FU7P/lmtyJ8MEU4WCxJIY5QXpkqi8xlTvucrScRVOL9FM7YSlxi84+bHcU5TuBJ2tg8CMrm7Oal6ZTFnpvLfLQwJLFuIWRLiTV3t1eebnK56Inb6l3fBYPL9cMlHD+U751/0XUOufvbd4/pukztITJx5xREBdEUCI5UcBhYXMuRQ7pKQBhMBzZTJRPACgmSmHICY+gu98gy5KRXOrT45f0Usg4ZOXtIlEhSKsAwFIRdy4+/vk2p3jNf6LIFthFQyZNUXykOJwT0zckPYVCXzrtomC4Xb4lTNuxq+JmBLw3punS0n/9te1D20Fz1G86OZ4B6zh3OberjCRaz/WNYe+TLfOXDbOt4DXuYTLEOkfsF9ioqAEativrqvT/klnDu0e/GBIJv81tuk9t3gDHzUq1qlZCsRP0sHfB+SBmOMW/Q0X48UYq2msa3G2jEMeYBY8wyhZjjfh0WaGjPVi6w5jQpvQdVA5T/b1A1o9g00HJEFXjGZtjaj5E4KPNz+7w2wwsSO4e2LvwFQSwMEFAAAAAgAbluIXPz1NO8vAgAA6wcAABgAAAB4bC93b3Jrc2hlZXRzL3NoZWV0MS54bWyNVdtymzAQ/RWGD4jwpY2bwczEpAl9SMdjT9LHjAxrUCMhKq3t5u8rYYdQRyJ5sqQ9Zy9nF298kOpZVwAY/BW81vOwQmyuCNF5BYLqC9lAbSxbqQRFc1Ul0Y0CWrQkwck4ir4SQVkdJnH7tlRJLHfIWQ1LFeidEFS9LIDLwzwcha8PK1ZW2D6QJG5oCWvAh8YQzJV0fgomoNZM1oGC7Ty8Hl1l05bRIh4ZHHTvHNhiNlI+28uPYh5GNifgkKN1Qc3PHlLg3Hoymfw5OQ3fglpm//zq/rat36S3oRpSyX+xAqt5OAuDArZ0x3ElDxmcavryluINRZrESh4CZYtN4twe2uht8QbOaivVGpWxMhMPExANly8AT6yICZp07DPJT+TFJ8k1FeCgp8P0Ahqq0KiODu7NMFcjxZ128L5/wKPcTISDd/sBL5fKVeLdMK1R8rcZCQcxGyYqKM0c/c8jprddg8ddg8e+7oxcHfWhrznLnT30EbKVq2s+9PGDcPXryLCf9D4ZRVEUk32/LX3ztzPjnS/a0lV65kOnPwd0nnQ6T3w6j106+9ALuXGp7IMv710q+9Cs9us86es8fqdz33x5rrM3O1fpmQ/9sB7QedrpPPXpPHHp7EOnVEnuUtpHcM+zD+3XedrXefRO5755NjvT2RfNPc/e0p3zTHpLwi7Be6pKVuuAw9Z4iS4uzSpRx61yvKBs2v+njUSUoj1WZhmDsgBj30qJ3cVutW6/J/8AUEsDBBQAAAAIAG5biFz39o8JpwIAAG0LAAANAAAAeGwvc3R5bGVzLnhtbN1W246bMBD9FcQHlE1QUahCpDbSSpXaaqXdh76aYIIlX6gxq2S/vjO2E5LsDt32saCE8RyfuTtkPbij5I8d5y45KKmHKu2c6z9l2bDruGLDB9NzDUhrrGIOlnafDb3lrBmQpGS2vLsrMsWETjdrPap75YZkZ0btqvQuTbLNujV6Ui3ToIC9TPHkmckq3TIpaivCZqaEPAb90mt2RhqbOIiGV+nCq4aXsGERlxhqtKWENtZrs+AmfNeRcIn4xwA7hJTX8YFis+6Zc9zqe1gEkte+xqL8dOwhvr1lx8XyY3rB8A9wUxvbcHvlKKg2a8lbhwwr9p0XnOnxURvnjEKpEWxvNAuRnGhXdN/IKnUdNGKydatFw7e66OVWfXYTBUhhx6V8xG0/23MeC8jj0Cah818b33Qs7EmE5KMYzMQFOrg0F4xf2F3+m91ePBv3ZYSMtF//Go3jD5a34uDXh3YKgDK/IMyDnvW9PH6WYq8VD9m/2+NmzU68pDNWvIA3nMkdKDiM7DO3TuxQA00KBTq0sUrnAvlyXdX+rE3wQFXpDzyo8iLRehTSCR1XnWgarl+3AOw7VsNPwZUD2NXwlo3SPZ3BKp3k77wRoyrPux6wFnHXJH/DUVwU02kGZ0I3/MCbbVzafe3FBARwG68wyDfQvb8IiGQFkIAQJH2RYZCswCN9/Y95rei8AkhGuHobWtGsFc0KvDehrb9JXwSrhItIuSzzvCjI8m63b4exJWtYFPghDJIRIof0hd7+tvIzAzAzNn+YDbLLs2NDpjwzomTKM5VHiKghcsqSGADSF3LIppAThUEQvnDUCFaeY5/JCMljPgOVJQnhkBLTWxRUoQq8iX6RhyjPy5KAECTCyHMSwgM7A5FhYCAklOfhRXrzPstO77ls+oO9+Q1QSwMEFAAAAAgAbluIXLdH64rAAAAAFgIAAAsAAABfcmVscy8ucmVsc52SS24CMQxArxJlX0ypxAIxrNiwQ4gLuInno5nEkWPE9PaN2MAgaBFL/56eLa8PNKB2HHPbpWzGMMRc2VY1rQCyaylgnnGiWCo1S0AtoTSQ0PXYECzm8yXILcNu1rdMc/xJ9AqR67pztGV3ChT1Afiuw5ojSkNa2XGAM0v/zdzPCtSana+s7PynNfCmzPP1IJCiR0VwLPSRpEyLdpSvPp7dvqTzpWNitHjf6P/z0KgUPfm/nTClidLXRQkmb7D5BVBLAwQUAAAACABuW4hc9nUBqjABAAApAgAADwAAAHhsL3dvcmtib29rLnhtbI2Q0U7DMAxFf6XKB9BugklM616YgEkIEEN7z1p3tZbEleNusK8nSSlM4oUnx9fWyb1enIgPO6JD9mGN83MuVSvSzfPcVy1Y7a+oAxdmDbHVElre59Q0WMGKqt6Ck3xaFLOcwWhBcr7FzquB9h+W7xh07VsAsWZAWY1OLRejs1fO8suOBKr4U1SjskU4+d+F2GZH9LhDg/JZqvQ2oDKLDi2eoS5VoTLf0umRGM/kRJtNxWRMqSbDYAssWP2RN9Hmu975pIjevcXMpZoVAdgge0kbia+DySOE5aHrhe7RCPBKCzww9R26fcKEGPlFjnSKsWZOWyhVoiYPoa7rwY8E0EU6nmMY8Lr+Ro6cGhp0UD8HkI+DkKoKJ40lkabXN5Pb4L435i5oL+6JdP1jbLzq8gtQSwMEFAAAAAgAbluIXDPr47qtAAAA+wEAABoAAAB4bC9fcmVscy93b3JrYm9vay54bWwucmVsc7WRPQ6DMAyFrxLlABio1KECpi6sFReIgvkRgUSxq8LtG8EASB26MFnPlr/3ZGcvNIp7O1HXOxLzaCbKZcfsHgCkOxwVRdbhFCaN9aPiIH0LTulBtQhpHN/BHxmyyI5MUS0O/yHapuk1Pq1+jzjxDzB8rB+oQ2QpKuVb5FzCbPY2wVqSKJClKOtc+rJOpIDLEhEvBmmPs+mTf3qlP4dd3O1XuTXPR7itIeD06+ILUEsDBBQAAAAIAG5biFybhkKEGwEAANcDAAATAAAAW0NvbnRlbnRfVHlwZXNdLnhtbK2Tz07DMAzGX6XqdWozOHBA6y6MK+zAC4TEXaPmn2JvdG+P27JKoLENlUujxvb3c/wlq7djBMw6Zz1WeUMUH4VA1YCTWIYIniN1SE4S/6adiFK1cgfifrl8ECp4Ak8F9Rr5erWBWu4tZc8db6MJvsoTWMyzpzGxZ1W5jNEaJYnj4uD1D0rxRSi5csjBxkRccEKeibOIIfQr4VT4eoCUjIZsKxO9SMdporMC6WgBy8saZ7oMdW0U6KD2jktKjAmkxgaAnC1H0cUVNPGQYfzezW5gkLlI5NRtChHZtQR/551s6auLyEKQyFw55IRk7dknhN5xDfpWOE/4I6R28ATFsMwf83efJ/1bGnkPof3ve9avpZPGTw2I4T2vPwFQSwECFAMUAAAACABuW4hcRsdNSJUAAADNAAAAEAAAAAAAAAAAAAAAgAEAAAAAZG9jUHJvcHMvYXBwLnhtbFBLAQIUAxQAAAAIAG5biFxZSoy46wAAAMsBAAARAAAAAAAAAAAAAACAAcMAAABkb2NQcm9wcy9jb3JlLnhtbFBLAQIUAxQAAAAIAG5biFyZXJwjEAYAAJwnAAATAAAAAAAAAAAAAACAAd0BAAB4bC90aGVtZS90aGVtZTEueG1sUEsBAhQDFAAAAAgAbluIXPz1NO8vAgAA6wcAABgAAAAAAAAAAAAAAICBHggAAHhsL3dvcmtzaGVldHMvc2hlZXQxLnhtbFBLAQIUAxQAAAAIAG5biFz39o8JpwIAAG0LAAANAAAAAAAAAAAAAACAAYMKAAB4bC9zdHlsZXMueG1sUEsBAhQDFAAAAAgAbluIXLdH64rAAAAAFgIAAAsAAAAAAAAAAAAAAIABVQ0AAF9yZWxzLy5yZWxzUEsBAhQDFAAAAAgAbluIXPZ1AaowAQAAKQIAAA8AAAAAAAAAAAAAAIABPg4AAHhsL3dvcmtib29rLnhtbFBLAQIUAxQAAAAIAG5biFwz6+O6rQAAAPsBAAAaAAAAAAAAAAAAAACAAZsPAAB4bC9fcmVscy93b3JrYm9vay54bWwucmVsc1BLAQIUAxQAAAAIAG5biFybhkKEGwEAANcDAAATAAAAAAAAAAAAAACAAYAQAABbQ29udGVudF9UeXBlc10ueG1sUEsFBgAAAAAJAAkAPgIAAMwRAAAAAA==";

function authHeaders(token) {
  return {
    Authorization: `Bearer ${token}`
  };
}

function jsonHeaders(token) {
  return {
    ...authHeaders(token),
    "Content-Type": "application/json"
  };
}

export function setup() {
  const loginResponse = http.post(
    `${BASE_URL}/auth/login`,
    JSON.stringify({
      user_id: WORKLOAD_USER,
      project_id: WORKLOAD_PROJECT,
      role: "admin",
      clearance: 9
    }),
    {
      headers: { "Content-Type": "application/json" }
    }
  );

  const loginOk = check(loginResponse, {
    "login request succeeded": (res) => res.status === 200,
    "login response contains token": (res) => Boolean(res.json("access_token"))
  });

  if (!loginOk) {
    throw new Error(`Login failed: status=${loginResponse.status} body=${loginResponse.body}`);
  }

  const token = String(loginResponse.json("access_token"));
  const workbookBytes = encoding.b64decode(PERF_XLSX_BASE64, "std");

  const uploadResponse = http.post(
    `${BASE_URL}/datasets/upload`,
    {
      user_id: WORKLOAD_USER,
      project_id: WORKLOAD_PROJECT,
      files: http.file(
        workbookBytes,
        "perf_employees.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      )
    },
    {
      headers: authHeaders(token)
    }
  );

  const uploadOk = check(uploadResponse, {
    "dataset upload succeeded": (res) => res.status === 200,
    "upload response contains dataset table": (res) => Boolean(res.json("dataset_table"))
  });

  if (!uploadOk) {
    throw new Error(`Upload failed: status=${uploadResponse.status} body=${uploadResponse.body}`);
  }

  return {
    token,
    datasetTable: String(uploadResponse.json("dataset_table"))
  };
}

export default function (setupData) {
  const scenario = exec.scenario.name;
  const response = http.post(
    `${BASE_URL}/chat/stream`,
    JSON.stringify({
      user_id: WORKLOAD_USER,
      project_id: WORKLOAD_PROJECT,
      dataset_table: setupData.datasetTable,
      message: "show headcount by department",
      request_id: `${scenario}-${__VU}-${__ITER}`
    }),
    {
      headers: jsonHeaders(setupData.token),
      tags: {
        endpoint: "chat_stream"
      }
    }
  );

  const isSuccess = check(response, {
    "chat stream status is 200": (res) => res.status === 200,
    "chat stream returns final event": (res) => String(res.body).includes("event: final")
  });

  QUERY_DURATION.add(response.timings.duration, { scenario });
  QUERY_FAILED.add(isSuccess ? 0 : 1, { scenario });

  sleep(0.2);
}
