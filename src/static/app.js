document.addEventListener("DOMContentLoaded", () => {
  const activitiesList = document.getElementById("activities-list");
  const messageDiv = document.getElementById("message");
  const categoryFilter = document.getElementById("category-filter");
  const sortOrder = document.getElementById("sort-order");
  const activitySearch = document.getElementById("activity-search");
  const userIcon = document.getElementById("user-icon");
  const accountPopover = document.getElementById("account-popover");
  const accountStatus = document.getElementById("account-status");
  const loginOpen = document.getElementById("login-open");
  const logoutButton = document.getElementById("logout-button");
  const loginDialog = document.getElementById("login-dialog");
  const loginForm = document.getElementById("login-form");
  const loginError = document.getElementById("login-error");
  let isTeacher = false;
  let activities = {};

  const weekdayOrder = {
    Monday: 0,
    Tuesday: 1,
    Wednesday: 2,
    Thursday: 3,
    Friday: 4,
    Saturday: 5,
    Sunday: 6,
  };

  function compareBySchedule([firstName, first], [secondName, second]) {
    const firstDay = first.schedule_days.length
      ? Math.min(...first.schedule_days.map((day) => weekdayOrder[day]))
      : Number.POSITIVE_INFINITY;
    const secondDay = second.schedule_days.length
      ? Math.min(...second.schedule_days.map((day) => weekdayOrder[day]))
      : Number.POSITIVE_INFINITY;

    return (
      firstDay - secondDay ||
      first.start_time.localeCompare(second.start_time) ||
      firstName.localeCompare(secondName)
    );
  }

  function renderActivities() {
    const searchTerm = activitySearch.value.trim().toLocaleLowerCase();
    const selectedCategory = categoryFilter.value;
    const sortedActivities = Object.entries(activities)
      .filter(([name, details]) => {
        const matchesCategory =
          !selectedCategory || details.category === selectedCategory;
        const searchableText = [
          name,
          details.description,
          details.schedule,
          details.category,
        ]
          .join(" ")
          .toLocaleLowerCase();

        return matchesCategory && searchableText.includes(searchTerm);
      })
      .sort(
        sortOrder.value === "schedule"
          ? compareBySchedule
          : ([firstName], [secondName]) =>
              firstName.localeCompare(secondName)
      );

    activitiesList.innerHTML = "";

    if (sortedActivities.length === 0) {
      activitiesList.innerHTML =
        "<p class=\"empty-state\">No activities match your filters.</p>";
      return;
    }

    sortedActivities.forEach(([name, details]) => {
      const activityCard = document.createElement("div");
      activityCard.className = "activity-card";

      const spotsLeft =
        details.max_participants - details.participants.length;
      const participantsHTML =
        details.participants.length > 0
          ? `<div class="participants-section">
              <h5>Participants:</h5>
              <ul class="participants-list">
                ${details.participants
                  .map(
                    (email) =>
                      `<li><span class="participant-email">${email}</span>${isTeacher ? `<button class="delete-btn" data-activity="${name}" data-email="${email}" aria-label="Unregister ${email} from ${name}">❌</button>` : ""}</li>`
                  )
                  .join("")}
              </ul>
            </div>`
          : "<p><em>No participants yet</em></p>";

      activityCard.innerHTML = `
        <h4>${name}</h4>
        <p class="activity-category">${details.category}</p>
        <p>${details.description}</p>
        <p><strong>Schedule:</strong> ${details.schedule}</p>
        <p><strong>Availability:</strong> ${spotsLeft} spots left</p>
        <div class="participants-container">
          ${participantsHTML}
        </div>
        ${isTeacher ? `
          <button type="button" class="register-student-toggle" aria-expanded="false">
            Register student
          </button>
          <form class="register-form hidden" data-activity="${name}">
            <label for="student-email-${encodeURIComponent(name)}">Student email</label>
            <input
              type="email"
              id="student-email-${encodeURIComponent(name)}"
              name="email"
              required
              placeholder="student@mergington.edu"
            />
            <div class="register-form-actions">
              <button type="submit">Register</button>
              <button type="button" class="secondary-button register-cancel">Cancel</button>
            </div>
          </form>
        ` : ""}
      `;

      activitiesList.appendChild(activityCard);
    });

    document.querySelectorAll(".delete-btn").forEach((button) => {
      button.addEventListener("click", handleUnregister);
    });
    document.querySelectorAll(".register-student-toggle").forEach((button) => {
      button.addEventListener("click", () => {
        const form = button.nextElementSibling;
        const isExpanded = button.getAttribute("aria-expanded") === "true";
        button.setAttribute("aria-expanded", String(!isExpanded));
        form.classList.toggle("hidden", isExpanded);
        if (!isExpanded) {
          form.querySelector("input").focus();
        }
      });
    });
    document.querySelectorAll(".register-cancel").forEach((button) => {
      button.addEventListener("click", () => {
        const form = button.closest(".register-form");
        form.classList.add("hidden");
        form.previousElementSibling.setAttribute("aria-expanded", "false");
        form.reset();
      });
    });
    document.querySelectorAll(".register-form").forEach((form) => {
      form.addEventListener("submit", handleRegister);
    });
  }

  function updateAccountUI(username = "") {
    isTeacher = Boolean(username);
    accountStatus.textContent = isTeacher
      ? `Logged in as ${username}`
      : "Students can view activities and participants.";
    loginOpen.classList.toggle("hidden", isTeacher);
    logoutButton.classList.toggle("hidden", !isTeacher);
    renderActivities();
  }

  async function refreshSession() {
    try {
      const response = await fetch("/auth/session");
      if (!response.ok) {
        throw new Error(`Failed to check teacher session: ${response.status}`);
      }
      const session = await response.json();
      updateAccountUI(session.authenticated ? session.username : "");
    } catch (error) {
      console.error("Error checking teacher session:", error);
    }
  }

  userIcon.addEventListener("click", () => {
    const isExpanded = userIcon.getAttribute("aria-expanded") === "true";
    userIcon.setAttribute("aria-expanded", String(!isExpanded));
    accountPopover.classList.toggle("hidden", isExpanded);
  });

  loginOpen.addEventListener("click", () => {
    accountPopover.classList.add("hidden");
    userIcon.setAttribute("aria-expanded", "false");
    loginError.classList.add("hidden");
    loginDialog.showModal();
  });

  document.getElementById("login-cancel").addEventListener("click", () => {
    loginDialog.close();
  });

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    loginError.classList.add("hidden");

    try {
      const response = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: document.getElementById("teacher-username").value,
          password: document.getElementById("teacher-password").value,
        }),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.detail || "Unable to log in.");
      }

      loginForm.reset();
      loginDialog.close();
      updateAccountUI(result.username);
    } catch (error) {
      loginError.textContent = error.message;
      loginError.classList.remove("hidden");
    }
  });

  logoutButton.addEventListener("click", async () => {
    try {
      const response = await fetch("/auth/logout", { method: "POST" });
      if (!response.ok) {
        throw new Error(`Unable to log out: ${response.status}`);
      }
      accountPopover.classList.add("hidden");
      userIcon.setAttribute("aria-expanded", "false");
      updateAccountUI();
    } catch (error) {
      accountStatus.textContent = error.message;
    }
  });

  categoryFilter.addEventListener("change", renderActivities);
  sortOrder.addEventListener("change", renderActivities);
  activitySearch.addEventListener("input", renderActivities);

  // Function to fetch activities from API
  async function fetchActivities() {
    try {
      const response = await fetch("/activities");
      if (!response.ok) {
        throw new Error(`Failed to load activities: ${response.status}`);
      }
      activities = await response.json();

      const selectedCategory = categoryFilter.value;
      const categories = [
        ...new Set(Object.values(activities).map(({ category }) => category)),
      ].sort((firstCategory, secondCategory) =>
        firstCategory.localeCompare(secondCategory)
      );
      categoryFilter.replaceChildren(new Option("All categories", ""));
      categories.forEach((category) => {
        categoryFilter.add(new Option(category, category));
      });
      categoryFilter.value = selectedCategory;

      renderActivities();
    } catch (error) {
      activitiesList.innerHTML =
        "<p>Failed to load activities. Please try again later.</p>";
      console.error("Error fetching activities:", error);
    }
  }

  // Handle unregister functionality
  async function handleUnregister(event) {
    const button = event.target;
    const activity = button.getAttribute("data-activity");
    const email = button.getAttribute("data-email");

    try {
      if (!isTeacher) {
        throw new Error("Teacher login required to unregister students.");
      }
      const response = await fetch(
        `/activities/${encodeURIComponent(
          activity
        )}/unregister?email=${encodeURIComponent(email)}`,
        {
          method: "DELETE",
        }
      );

      const result = await response.json();

      if (response.ok) {
        messageDiv.textContent = result.message;
        messageDiv.className = "success";

        // Refresh activities list to show updated participants
        fetchActivities();
      } else {
        if (response.status === 401) {
          updateAccountUI();
        }
        messageDiv.textContent = result.detail || "An error occurred";
        messageDiv.className = "error";
      }

      messageDiv.classList.remove("hidden");

      // Hide message after 5 seconds
      setTimeout(() => {
        messageDiv.classList.add("hidden");
      }, 5000);
    } catch (error) {
      messageDiv.textContent =
        error.message.includes("Teacher login required")
          ? error.message
          : "Failed to unregister. Please try again.";
      messageDiv.className = "error";
      messageDiv.classList.remove("hidden");
      if (error.message.includes("Teacher login required")) {
        updateAccountUI();
      }
      console.error("Error unregistering:", error);
    }
  }

  async function handleRegister(event) {
    event.preventDefault();
    if (!isTeacher) {
      updateAccountUI();
      return;
    }

    const form = event.currentTarget;
    const activity = form.dataset.activity;
    const email = new FormData(form).get("email");

    try {
      const response = await fetch(
        `/activities/${encodeURIComponent(
          activity
        )}/signup?email=${encodeURIComponent(email)}`,
        {
          method: "POST",
        }
      );

      const result = await response.json();

      if (response.ok) {
        messageDiv.textContent = result.message;
        messageDiv.className = "success";
        form.reset();
        fetchActivities();
      } else {
        if (response.status === 401) {
          updateAccountUI();
        }
        messageDiv.textContent = result.detail || "An error occurred";
        messageDiv.className = "error";
      }

      messageDiv.classList.remove("hidden");

      // Hide message after 5 seconds
      setTimeout(() => {
        messageDiv.classList.add("hidden");
      }, 5000);
    } catch (error) {
      messageDiv.textContent = "Failed to sign up. Please try again.";
      messageDiv.className = "error";
      messageDiv.classList.remove("hidden");
      console.error("Error signing up:", error);
    }
  }

  // Initialize app
  fetchActivities();
  refreshSession();
});
