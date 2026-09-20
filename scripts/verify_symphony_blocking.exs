# Separate VM only: exercise the real orchestrator callbacks without dispatching tasks.
alias SymphonyElixir.{Orchestrator, Workflow, WorkflowStore}
alias SymphonyElixir.Orchestrator.State
alias SymphonyElixir.Tracker.Issue

Application.ensure_all_started(:logger)
Workflow.set_workflow_file_path("/config/WORKFLOW.md")
{:ok, _} = WorkflowStore.start_link([])

check = fn condition, label ->
  unless condition, do: raise("FAIL: " <> label)
end

run = fn events, expected ->
  ref = make_ref()
  now = DateTime.utc_now()
  entry = %{pid: self(), ref: ref, identifier: "GH-SYNTHETIC", session_id: "test-turn",
    issue: %Issue{id: "synthetic", identifier: "GH-SYNTHETIC", state: "open"},
    started_at: now, last_codex_timestamp: now, last_codex_event: nil, last_codex_message: nil}
  initial = %State{running: %{"synthetic" => entry}, claimed: MapSet.new(["synthetic"]),
    codex_totals: %{input_tokens: 0, output_tokens: 0, total_tokens: 0, seconds_running: 0}}
  state = Enum.reduce(events, initial, fn event, state ->
    {:noreply, next} = Orchestrator.handle_info(
      {:codex_worker_update, "synthetic", Map.put(event, :timestamp, now)}, state)
    next
  end)
  {:noreply, result} = Orchestrator.handle_info({:DOWN, ref, :process, self(), :synthetic_failure}, state)
  check.(Map.has_key?(result.blocked, "synthetic") == expected, "blocked classification")
  check.(Map.has_key?(result.retry_attempts, "synthetic") != expected, "retry classification")
  check.(not Map.has_key?(result.running, "synthetic"), "worker removed")
  if expected, do: check.(MapSet.member?(result.claimed, "synthetic"), "blocked stays claimed")
end

for kind <- [:turn_input_required, :approval_required] do
  run.([%{event: kind}, %{event: :turn_ended_with_error, reason: {kind, %{}}},
        %{event: :notification}], true)
  run.([%{event: :turn_ended_with_error, reason: {kind, %{}}}], true)
end
run.([%{event: :turn_ended_with_error, reason: :timeout}], false)
run.([%{event: :notification}], false)
IO.puts("PASS: 6 blocker/retry sequences; input and approval survive error/notification; ordinary failures retry")

root = Path.join(System.tmp_dir!(), "symphony-control-" <> Integer.to_string(System.unique_integer([:positive])))
File.mkdir_p!(Path.join(root, "GH-987654321"))
System.put_env("SYMPHONY_CONTROL_ROOT", root)
check.(SymphonyElixir.Codex.AppServer.controlled_turn_timeout() == :infinity, "controlled turns have no duration ceiling")
issue = %Issue{id: "persistent", identifier: "GH-987654321", state: "open", labels: ["symphony:ready"]}
for status <- ["review", "blocked"] do
  File.write!(Path.join([root, issue.identifier, "state.json"]), Jason.encode!(%{status: status}))
  check.(not Orchestrator.should_dispatch_issue_for_test(issue, %State{}), "terminal state blocks fresh dispatch")
  state = %State{claimed: MapSet.new([issue.id])}
  result = Orchestrator.handle_retry_issue_lookup_for_test(issue, state, issue.id, 2, %{})
  check.(not MapSet.member?(result.claimed, issue.id), "terminal retry releases claim")
  check.(map_size(result.retry_attempts) == 0, "terminal retry is not scheduled again")
end
System.delete_env("SYMPHONY_CONTROL_ROOT")
check.(is_integer(SymphonyElixir.Codex.AppServer.controlled_turn_timeout()), "legacy timeout retained outside controlled mode")
File.rm_rf!(root)
IO.puts("PASS: persistent review/blocked state prevents dispatch and retry with ready still present")
