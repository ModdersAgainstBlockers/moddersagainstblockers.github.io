import { request } from "@octokit/request";
import { readFileSync } from "fs";
import jwt from "jsonwebtoken";

// Read environment variables
const appId = process.env.APP_ID;
const privateKey = readFileSync('private_key.pem', 'utf-8');
const workflowIds = JSON.parse(readFileSync('workflow_ids.json', 'utf-8'));

async function generateJWT(appId, privateKey) {
    const payload = {
        iat: Math.floor(Date.now() / 1000),
        exp: Math.floor(Date.now() / 1000) + (10 * 60), // 10 minutes
        iss: appId
    };
    return jwt.sign(payload, privateKey, { algorithm: 'RS256' });
}

async function getInstallations(jwt) {
    const response = await request("GET /app/installations", {
        headers: {
            authorization: `Bearer ${jwt}`,
            accept: "application/vnd.github.v3+json"
        }
    });
    return response.data;
}

async function getAccessToken(jwt, installationId) {
    const response = await request("POST /app/installations/{installation_id}/access_tokens", {
        headers: {
            authorization: `Bearer ${jwt}`,
            accept: "application/vnd.github.v3+json"
        },
        installation_id: installationId
    });
    return response.data.token;
}

async function getRepositories(accessToken) {
    const response = await request("GET /installation/repositories", {
        headers: {
            authorization: `token ${accessToken}`,
            accept: "application/vnd.github.v3+json"
        }
    });
    return response.data.repositories;
}

async function triggerWorkflow(repo, accessToken, data) {
    await request("POST /repos/{owner}/{repo}/dispatches", {
        headers: {
            authorization: `token ${accessToken}`,
            accept: "application/vnd.github.v3+json"
        },
        owner: repo.split('/')[0],
        repo: repo.split('/')[1],
        event_type: "custom_event",
        client_payload: data
    });
}

async function main() {
    const jwt = await generateJWT(appId, privateKey);
    const installations = await getInstallations(jwt);

    for (const installation of installations) {
        const accessToken = await getAccessToken(jwt, installation.id);
        const repositories = await getRepositories(accessToken);

        for (const repo of repositories) {
            const repoName = repo.full_name.toLowerCase();
            const customData = workflowIds[repoName];
            if (customData) {
                const customDataObj = {"data": customData}
                console.log(`Triggering workflow for ${repo.full_name}`);
                await triggerWorkflow(repo.full_name, accessToken, customDataObj);
            } else {
                console.log(`No data found for ${repoName} in workflow_ids.json`);
            }
        }
    }
}

main().catch(err => {
    console.error(err);
    process.exit(1);
});